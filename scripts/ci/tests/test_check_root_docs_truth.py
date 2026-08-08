"""Tests for check_root_docs_truth.py — the Layer 1 commit-time gate for the seven root
operator/governance docs.

Deliberately thin: the detection logic itself is tested in
scripts/pipeline/tests/test_root_docs_checks.py (the shared module this gate imports from).
These tests cover only this file's own orchestration (which checks apply to which file,
--staged scoping, exit codes) — testing the imported detection logic again here would just
duplicate that suite and let it silently drift out of sync.
"""
from __future__ import annotations

import subprocess
import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "checks"))

import check_root_docs_truth as crt  # noqa: E402


@pytest.fixture(autouse=True)
def _reset_configure():
    yield
    crt.configure()


def _run_git(args, cwd):
    result = subprocess.run(["git", *args], cwd=str(cwd), capture_output=True, text=True, timeout=30)
    assert result.returncode == 0, f"git {args} failed: {result.stderr}"
    return result.stdout.strip()


def _write(path: Path, text: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(text, encoding="utf-8")


def _build_repo(tmp_path: Path) -> Path:
    repo = tmp_path / "repo"
    repo.mkdir()
    _run_git(["init", "-q"], cwd=repo)
    _run_git(["config", "user.email", "test@example.com"], cwd=repo)
    _run_git(["config", "user.name", "Test"], cwd=repo)

    _write(repo / "docs" / "registries" / "skills.md", "| content-check | S-23 | audit |\n")
    _write(repo / "OPERATOR_GUIDE.md", "# Guide\n\nSee data/products.json for the count.\n")
    _write(repo / "RUNBOOK.md", "# Runbook\n")
    _write(repo / "CODEX.md", "# Codex\n")
    _write(repo / "GRADE_CONTRACT.md", "No frozen baseline mentioned.\n")

    _run_git(["add", "-A"], cwd=repo)
    _run_git(["commit", "-q", "-m", "initial"], cwd=repo)
    return repo


# ---------------------------------------------------------------------------
# check_file orchestration
# ---------------------------------------------------------------------------


def test_check_file_flags_dead_path(tmp_path):
    repo = _build_repo(tmp_path)
    crt.configure(repo_root=repo)
    (repo / "RUNBOOK.md").write_text(
        "```bash\npython scripts/translator/cli.py batch\n```\n", encoding="utf-8"
    )
    result = crt.check_file("RUNBOOK.md")
    assert len(result["hard_gate"]) == 1
    assert result["hard_gate"][0]["check"] == "check_dead_path_references"


def test_check_file_clean_file_has_no_hard_gate_findings(tmp_path):
    repo = _build_repo(tmp_path)
    crt.configure(repo_root=repo)
    result = crt.check_file("OPERATOR_GUIDE.md")
    assert result["hard_gate"] == []


def test_check_file_missing_file_reports_not_exists(tmp_path):
    repo = _build_repo(tmp_path)
    crt.configure(repo_root=repo)
    result = crt.check_file("LAYMAN_SYSTEM_STATUS_REVIEW.md")
    assert result["exists"] is False
    assert result["hard_gate"] == []


def test_check_file_grade_contract_sync_only_applies_to_grade_contract(tmp_path):
    repo = _build_repo(tmp_path)
    crt.configure(repo_root=repo)
    # RUNBOOK.md mentioning "EVALUATOR_FREEZE_VERSION" text must not trigger the
    # GRADE_CONTRACT.md-specific sync check.
    (repo / "RUNBOOK.md").write_text("Mentions EVALUATOR_FREEZE_VERSION in passing.\n", encoding="utf-8")
    result = crt.check_file("RUNBOOK.md")
    assert not any(f["check"] == "check_grade_contract_sync" for f in result["hard_gate"])


# ---------------------------------------------------------------------------
# main() — exit codes and --staged scoping
# ---------------------------------------------------------------------------


def test_main_exits_zero_on_clean_repo(tmp_path, capsys):
    repo = _build_repo(tmp_path)
    crt.configure(repo_root=repo)
    exit_code = crt.main([])
    assert exit_code == 0


def test_main_exits_one_on_hard_gate_finding(tmp_path, capsys):
    repo = _build_repo(tmp_path)
    crt.configure(repo_root=repo)
    (repo / "RUNBOOK.md").write_text(
        "```bash\npython scripts/translator/cli.py batch\n```\n", encoding="utf-8"
    )
    exit_code = crt.main([])
    assert exit_code == 1
    captured = capsys.readouterr()
    assert "RUNBOOK.md" in captured.err


def test_main_staged_flag_scopes_to_staged_files_only(tmp_path, capsys):
    repo = _build_repo(tmp_path)
    crt.configure(repo_root=repo)
    # Introduce a hard-gate finding in RUNBOOK.md but only stage OPERATOR_GUIDE.md.
    (repo / "RUNBOOK.md").write_text(
        "```bash\npython scripts/translator/cli.py batch\n```\n", encoding="utf-8"
    )
    (repo / "OPERATOR_GUIDE.md").write_text(
        "# Guide (edited)\n\nSee data/products.json for the count.\n", encoding="utf-8"
    )
    _run_git(["add", "OPERATOR_GUIDE.md"], cwd=repo)
    exit_code = crt.main(["--staged"])
    assert exit_code == 0, "RUNBOOK.md's violation must not block a commit that never staged it"


def test_main_json_output_is_valid(tmp_path, capsys):
    repo = _build_repo(tmp_path)
    crt.configure(repo_root=repo)
    exit_code = crt.main(["--json"])
    assert exit_code == 0
    import json
    payload = json.loads(capsys.readouterr().out)
    assert "total_hard_gate" in payload
    assert payload["total_hard_gate"] == 0
