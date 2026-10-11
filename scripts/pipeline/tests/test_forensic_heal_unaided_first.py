"""Negative-control tests for scripts/pipeline/lib/forensic_heal/manual_first_audit.py --
the L2 (skill-invocation ledger audit) and L3 (artifact-mtime forensics) layers of S-122's
unaided-first gate. The whole point of this module is that it must actually TRIP on a real
violation, not just structurally exist -- these tests prove both violation classes fire and
that a missing ledger reports UNPROVABLE rather than a silent CLEAN.
"""
from __future__ import annotations

import json
import sys
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "lib" / "forensic_heal"))

import manual_first_audit as mfa  # noqa: E402


def _write(path: Path, data) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    if isinstance(data, str):
        path.write_text(data, encoding="utf-8")
    else:
        path.write_text(json.dumps(data), encoding="utf-8")


# ---------------------------------------------------------------------------
# L3: artifact-mtime forensics
# ---------------------------------------------------------------------------


def test_census_is_empty_dict_for_absent_roots(tmp_path):
    census = mfa.census_artifacts(tmp_path)
    assert census == {"full": {}, "shallow": {}}


def test_diff_detects_new_file_in_a_full_census_root(tmp_path):
    before = mfa.census_artifacts(tmp_path)
    _write(tmp_path / "reports" / "audit" / "run1" / "result.json", {"ok": True})
    after = mfa.census_artifacts(tmp_path)

    violations = mfa.diff_census(before, after)
    assert any(v["kind"] == "new_file" and "reports/audit" in v["path"] for v in violations)


def test_diff_detects_modified_file_in_a_full_census_root(tmp_path):
    f = tmp_path / "reports" / "gap-eval" / "result.json"
    _write(f, {"v": 1})
    before = mfa.census_artifacts(tmp_path)

    time.sleep(0.01)
    f.write_text(json.dumps({"v": 2}), encoding="utf-8")
    after = mfa.census_artifacts(tmp_path)

    violations = mfa.diff_census(before, after)
    assert any(v["kind"] == "modified_file" for v in violations)


def test_diff_is_empty_when_nothing_changed(tmp_path):
    _write(tmp_path / "reports" / "truth-audit" / "a.json", {"x": 1})
    before = mfa.census_artifacts(tmp_path)
    after = mfa.census_artifacts(tmp_path)
    assert mfa.diff_census(before, after) == []


def test_diff_detects_touched_shallow_subtree_under_knowledge(tmp_path):
    f = tmp_path / "knowledge" / "pdf" / "net" / "merged" / "model.yaml"
    _write(f, "stats: {}\n")
    before = mfa.census_artifacts(tmp_path)

    time.sleep(0.01)
    f.write_text("stats: {touched: true}\n", encoding="utf-8")
    after = mfa.census_artifacts(tmp_path)

    violations = mfa.diff_census(before, after)
    assert any(v["layer"] == "L3" and v["kind"] == "touched_subtree" for v in violations)


def test_diff_detects_new_shallow_subtree_under_runs(tmp_path):
    before = mfa.census_artifacts(tmp_path)
    _write(tmp_path / "runs" / ".clone_cache" / "aspose_pdf_net" / "README.md", "# readme\n")
    after = mfa.census_artifacts(tmp_path)

    violations = mfa.diff_census(before, after)
    assert any(v["kind"] == "new_subtree" for v in violations)


def test_git_dir_is_excluded_from_census(tmp_path):
    _write(tmp_path / "reports" / "audit" / ".git" / "HEAD", "ref: refs/heads/main\n")
    census = mfa.census_artifacts(tmp_path)
    assert census["full"] == {}


# ---------------------------------------------------------------------------
# L2: skill-invocation ledger audit
# ---------------------------------------------------------------------------


def test_audit_ledger_flags_system_skill_started_inside_window(tmp_path):
    _write(
        tmp_path / "reports" / "skill-context" / "history" / "20260808-120000-S-90.json",
        {
            "skill_id": "S-90", "context_type": "skill", "scope_patterns": ["content/**"],
            "started_at": "2026-08-08T12:00:30Z", "ended_at": "2026-08-08T12:01:00Z",
            "end_status": "completed",
        },
    )
    violations, readable = mfa.audit_ledger(
        tmp_path, window_start="2026-08-08T12:00:00Z", window_end="2026-08-08T12:30:00Z",
    )
    assert readable is True
    assert len(violations) == 1
    assert violations[0]["layer"] == "L2"
    assert "S-90" in violations[0]["skill_ids"]


def test_audit_ledger_flags_system_skill_from_skill_runs_list(tmp_path):
    _write(
        tmp_path / "reports" / "skill-runs" / "20260808-120500-s85.json",
        {
            "run_id": "20260808-120500-s85", "skills_invoked": ["S-85"],
            "started_at": "2026-08-08T12:05:00Z", "completed_at": "2026-08-08T12:06:00Z",
        },
    )
    violations, readable = mfa.audit_ledger(
        tmp_path, window_start="2026-08-08T12:00:00Z", window_end="2026-08-08T12:30:00Z",
    )
    assert readable is True
    assert any("S-85" in v["skill_ids"] for v in violations)


def test_audit_ledger_ignores_record_started_before_window(tmp_path):
    _write(
        tmp_path / "reports" / "skill-context" / "history" / "20260808-115000-S-90.json",
        {"skill_id": "S-90", "started_at": "2026-08-08T11:50:00Z", "ended_at": "2026-08-08T11:59:00Z"},
    )
    violations, readable = mfa.audit_ledger(
        tmp_path, window_start="2026-08-08T12:00:00Z", window_end="2026-08-08T12:30:00Z",
    )
    assert readable is True
    assert violations == []


def test_audit_ledger_ignores_non_system_skill_in_window(tmp_path):
    # S-76 (/commit) is not a system-tooling skill for unaided-first purposes.
    _write(
        tmp_path / "reports" / "skill-context" / "history" / "20260808-121000-S-76.json",
        {"skill_id": "S-76", "started_at": "2026-08-08T12:10:00Z", "ended_at": "2026-08-08T12:11:00Z"},
    )
    violations, readable = mfa.audit_ledger(
        tmp_path, window_start="2026-08-08T12:00:00Z", window_end="2026-08-08T12:30:00Z",
    )
    assert readable is True
    assert violations == []


def test_audit_ledger_unreadable_when_no_ledger_dirs_exist(tmp_path):
    violations, readable = mfa.audit_ledger(
        tmp_path, window_start="2026-08-08T12:00:00Z", window_end="2026-08-08T12:30:00Z",
    )
    assert readable is False
    assert violations == []


def test_audit_ledger_readable_when_dir_present_but_empty(tmp_path):
    (tmp_path / "reports" / "skill-context" / "history").mkdir(parents=True)
    violations, readable = mfa.audit_ledger(
        tmp_path, window_start="2026-08-08T12:00:00Z", window_end="2026-08-08T12:30:00Z",
    )
    assert readable is True
    assert violations == []


def test_audit_ledger_flags_unreadable_individual_record(tmp_path):
    (tmp_path / "reports" / "skill-context" / "history").mkdir(parents=True)
    (tmp_path / "reports" / "skill-context" / "history" / "torn.json").write_text("{not json", encoding="utf-8")
    violations, readable = mfa.audit_ledger(
        tmp_path, window_start="2026-08-08T12:00:00Z", window_end="2026-08-08T12:30:00Z",
    )
    assert readable is True
    assert any(v["kind"] == "unreadable_ledger_record" for v in violations)


# ---------------------------------------------------------------------------
# Combined verdict
# ---------------------------------------------------------------------------


def test_evaluate_unaided_first_is_unprovable_with_no_ledger_and_no_artifact_changes(tmp_path):
    before_census = mfa.census_artifacts(tmp_path)
    result = mfa.evaluate_unaided_first(
        tmp_path, window_start="2026-08-08T12:00:00Z", window_end="2026-08-08T12:30:00Z",
        before_census=before_census,
    )
    assert result["verdict"] == "UNPROVABLE"
    assert result["violations"] == []


def test_evaluate_unaided_first_is_clean_when_ledger_present_and_nothing_changed(tmp_path):
    (tmp_path / "reports" / "skill-context" / "history").mkdir(parents=True)
    (tmp_path / "reports" / "skill-runs").mkdir(parents=True)
    before_census = mfa.census_artifacts(tmp_path)
    result = mfa.evaluate_unaided_first(
        tmp_path, window_start="2026-08-08T12:00:00Z", window_end="2026-08-08T12:30:00Z",
        before_census=before_census,
    )
    assert result["verdict"] == "UNAIDED_FIRST_CLEAN"


def test_evaluate_unaided_first_violated_wins_over_unprovable(tmp_path):
    # No ledger dirs (would be UNPROVABLE on its own) AND a real L3 artifact violation --
    # a proven violation must win over "absence of evidence".
    before_census = mfa.census_artifacts(tmp_path)
    _write(tmp_path / "reports" / "audit" / "sneaky.json", {"ran": True})
    result = mfa.evaluate_unaided_first(
        tmp_path, window_start="2026-08-08T12:00:00Z", window_end="2026-08-08T12:30:00Z",
        before_census=before_census,
    )
    assert result["verdict"] == "VIOLATED"
    assert any(v["layer"] == "L3" for v in result["violations"])
