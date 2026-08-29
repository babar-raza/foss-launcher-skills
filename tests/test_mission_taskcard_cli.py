"""Tests for scripts/pipeline/commands/ops/mission_taskcard_cli.py (new
2026-08-29, TASK_BACKLOG.md SYNC-1)."""
import sys
from pathlib import Path

import pytest

REPO_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(REPO_ROOT / "scripts" / "pipeline" / "commands" / "ops"))
sys.path.insert(0, str(REPO_ROOT / "scripts" / "pipeline" / "lib"))

import mission_taskcard_cli as cli  # noqa: E402
from taskcard_store import TaskcardStore  # noqa: E402


@pytest.fixture(autouse=True)
def _isolate(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    yield tmp_path


def test_append_then_list(capsys):
    code = cli.main(["append", "--mission-id", "M-1", "--task-id", "T-1", "--status", "TODO", "--recorded-by", "me"])
    assert code == 0
    capsys.readouterr()

    code = cli.main(["list", "--mission-id", "M-1"])
    assert code == 0
    out = capsys.readouterr().out
    assert "T-1: TODO" in out


def test_advance_success(capsys):
    cli.main(["append", "--mission-id", "M-1", "--task-id", "T-1", "--status", "TODO", "--recorded-by", "me"])
    capsys.readouterr()
    code = cli.main(["advance", "--mission-id", "M-1", "--task-id", "T-1", "--from", "TODO", "--to", "READY", "--recorded-by", "me"])
    assert code == 0
    out = capsys.readouterr().out
    assert '"status": "READY"' in out


def test_advance_cas_conflict_returns_2(capsys):
    cli.main(["append", "--mission-id", "M-1", "--task-id", "T-1", "--status", "TODO", "--recorded-by", "me"])
    cli.main(["advance", "--mission-id", "M-1", "--task-id", "T-1", "--from", "TODO", "--to", "READY", "--recorded-by", "me"])
    capsys.readouterr()
    code = cli.main(["advance", "--mission-id", "M-1", "--task-id", "T-1", "--from", "TODO", "--to", "IN_PROGRESS", "--recorded-by", "other"])
    assert code == 2
    assert "CAS CONFLICT" in capsys.readouterr().err


def test_advance_not_found_returns_1(capsys):
    code = cli.main(["advance", "--mission-id", "M-1", "--task-id", "GHOST", "--from", "TODO", "--to", "READY", "--recorded-by", "me"])
    assert code == 1
    assert "NOT FOUND" in capsys.readouterr().err


def test_pause_creates_row(capsys):
    code = cli.main(["pause", "--mission-id", "M-1", "--task-id", "T-1", "--reason", "blocked on X", "--recorded-by", "me"])
    assert code == 0
    cli.main(["list", "--mission-id", "M-1"])
    out = capsys.readouterr().out
    assert "T-1: PAUSED" in out


def test_pause_no_create_missing_returns_1(capsys):
    code = cli.main(["pause", "--mission-id", "M-1", "--task-id", "GHOST", "--reason", "x", "--recorded-by", "me", "--no-create"])
    assert code == 1


def test_list_empty_mission_returns_0(capsys):
    code = cli.main(["list", "--mission-id", "NEVER-SEEN"])
    assert code == 0
    assert "No taskcards recorded" in capsys.readouterr().err


def test_append_invalid_status_returns_1(capsys):
    code = cli.main(["append", "--mission-id", "M-1", "--task-id", "T-1", "--status", "NOT_REAL", "--recorded-by", "me"])
    assert code == 1
    assert "ERROR" in capsys.readouterr().err
