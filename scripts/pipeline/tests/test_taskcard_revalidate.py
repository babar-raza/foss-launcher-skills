"""Tests for taskcard_revalidate.py (MT069 HC-15)."""
from __future__ import annotations

import sys
from dataclasses import dataclass
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from commands.governance import taskcard_revalidate as tr  # noqa: E402
from commands.governance.taskcard_revalidate import cards_with_revalidation, main, run_check  # noqa: E402
from lib.taskcard_store import TaskcardStore  # noqa: E402


@dataclass
class _FakeCompletedProcess:
    returncode: int
    stdout: str = ""
    stderr: str = ""


class _FakeRunner:
    def __init__(self, by_command: dict):
        self._by_command = by_command
        self.calls: "list[str]" = []

    def __call__(self, command, **kwargs):
        self.calls.append(command)
        return self._by_command.get(command, _FakeCompletedProcess(0))


def _seed(tmp_path, mission, task_id, status="IMPLEMENTED", revalidate=None):
    store = TaskcardStore(mission, repo_root=tmp_path)
    store.append({"task_id": task_id, "mission_id": mission, "status": "TODO", "title": "t",
                  "description": "d", "dependencies": [], "recorded_at": "2026-09-23T00:00:00Z",
                  "recorded_by": "test", "evidence_refs": []})
    extra = {"revalidate": revalidate} if revalidate else {}
    store.update_taskcard_status(task_id, expected_status="TODO", new_status=status,
                                  recorded_by="test", evidence_refs=["test evidence"], **extra)


class TestDefaultRepoRoot:
    def test_default_repo_root_points_at_the_real_repo_not_a_scripts_subdirectory(self):
        """Regression: parents[N] off-by-one previously resolved to .../scripts instead of the repo
        root, so the default path silently pointed at a directory with no reports/ at all and every
        real invocation (no --repo-root override) found zero cards regardless of the real ledger."""
        assert (tr._REPO_ROOT / "reports").is_dir()
        assert (tr._REPO_ROOT / "scripts" / "pipeline").is_dir()
        assert tr._REPO_ROOT.name != "scripts"


class TestCardsWithRevalidation:
    def test_a_mission_with_no_ledger_has_no_cards(self, tmp_path):
        assert cards_with_revalidation("nope", repo_root=tmp_path) == []

    def test_only_cards_declaring_revalidate_are_returned(self, tmp_path):
        _seed(tmp_path, "M1", "T-1", revalidate="echo ok")
        _seed(tmp_path, "M1", "T-2")  # no revalidate field
        cards = cards_with_revalidation("M1", repo_root=tmp_path)
        assert [c["task_id"] for c in cards] == ["T-1"]

    def test_only_the_latest_row_per_task_is_considered(self, tmp_path):
        store = TaskcardStore("M2", repo_root=tmp_path)
        store.append({"task_id": "T-1", "mission_id": "M2", "status": "TODO", "title": "t",
                      "description": "d", "dependencies": [], "recorded_at": "2026-09-23T00:00:00Z",
                      "recorded_by": "test", "evidence_refs": []})
        store.update_taskcard_status("T-1", expected_status="TODO", new_status="IN_PROGRESS",
                                      recorded_by="test", revalidate="echo stale")
        store.update_taskcard_status("T-1", expected_status="IN_PROGRESS", new_status="IMPLEMENTED",
                                      recorded_by="test", evidence_refs=["e"], revalidate="echo current")
        cards = cards_with_revalidation("M2", repo_root=tmp_path)
        assert len(cards) == 1 and cards[0]["revalidate"] == "echo current"


class TestRunCheck:
    def test_a_passing_command_reports_passed_true(self, tmp_path):
        runner = _FakeRunner({"echo hi": _FakeCompletedProcess(0, stdout="hi\n")})
        passed, tail = run_check("echo hi", repo_root=tmp_path, runner=runner)
        assert passed is True and "hi" in tail

    def test_a_failing_command_reports_passed_false_with_output(self, tmp_path):
        runner = _FakeRunner({"false": _FakeCompletedProcess(1, stderr="boom\n")})
        passed, tail = run_check("false", repo_root=tmp_path, runner=runner)
        assert passed is False and "boom" in tail

    def test_output_tail_is_capped_to_the_last_15_lines(self, tmp_path):
        long_output = "\n".join(f"line{i}" for i in range(100))
        runner = _FakeRunner({"noisy": _FakeCompletedProcess(1, stdout=long_output)})
        _, tail = run_check("noisy", repo_root=tmp_path, runner=runner)
        assert tail.count("\n") + 1 == 15
        assert "line99" in tail and "line0" not in tail

    def test_pythonpath_is_injected_so_declared_commands_never_need_a_shell_specific_prefix(self, tmp_path):
        """Regression: a declared check written as 'PYTHONPATH=scripts/pipeline python -m pytest ...'
        (this repo's universal convention) silently failed under shell=True on Windows, which invokes
        cmd.exe -- it does not understand the Unix inline VAR=value prefix. A REAL subprocess call
        (not the fake runner) proves the injected env, using python itself to read the variable
        portably instead of a shell-specific `echo $VAR` / `echo %VAR%`."""
        import subprocess as real_subprocess
        cmd = f'"{sys.executable}" -c "import os,sys; sys.exit(0 if os.environ.get(\'PYTHONPATH\',\'\').endswith(\'pipeline\') else 1)"'
        passed, _ = run_check(cmd, repo_root=tmp_path, runner=real_subprocess.run)
        assert passed is True


class TestMainCLI:
    def test_exits_0_when_nothing_declared(self, tmp_path, capsys):
        assert main(["--mission", "M3", "--repo-root", str(tmp_path)]) == 0
        assert "No revalidation checks declared" in capsys.readouterr().out

    def test_exits_0_when_every_declared_check_still_passes(self, tmp_path):
        _seed(tmp_path, "M4", "T-1", revalidate="echo ok")
        runner = _FakeRunner({"echo ok": _FakeCompletedProcess(0)})
        assert main(["--mission", "M4", "--repo-root", str(tmp_path)], runner=runner) == 0

    def test_exits_1_and_names_the_card_when_a_declared_check_now_fails(self, tmp_path, capsys):
        _seed(tmp_path, "M5", "T-1", revalidate="pytest broken_test.py")
        runner = _FakeRunner({"pytest broken_test.py": _FakeCompletedProcess(1, stderr="1 failed")})
        rc = main(["--mission", "M5", "--repo-root", str(tmp_path)], runner=runner)
        out = capsys.readouterr().out
        assert rc == 1
        assert "T-1" in out and "FAIL" in out
        assert "ledger status may be stale" in out

    def test_task_filter_narrows_to_one_card(self, tmp_path):
        _seed(tmp_path, "M6", "T-1", revalidate="echo a")
        _seed(tmp_path, "M6", "T-2", revalidate="echo b")
        runner = _FakeRunner({"echo a": _FakeCompletedProcess(0), "echo b": _FakeCompletedProcess(0)})
        main(["--mission", "M6", "--task", "T-1", "--repo-root", str(tmp_path)], runner=runner)
        assert runner.calls == ["echo a"]

    def test_json_output_lists_only_the_failing_cards(self, tmp_path, capsys):
        _seed(tmp_path, "M7", "T-1", revalidate="echo a")
        _seed(tmp_path, "M7", "T-2", revalidate="echo b")
        runner = _FakeRunner({"echo a": _FakeCompletedProcess(0), "echo b": _FakeCompletedProcess(1)})
        rc = main(["--mission", "M7", "--repo-root", str(tmp_path), "--json"], runner=runner)
        import json
        out = json.loads(capsys.readouterr().out)
        assert rc == 1
        assert out["checked"] == 2
        assert [f["task_id"] for f in out["failing"]] == ["T-2"]

    def test_this_tool_never_writes_to_the_ledger(self, tmp_path):
        _seed(tmp_path, "M8", "T-1", revalidate="false", status="IMPLEMENTED")
        runner = _FakeRunner({"false": _FakeCompletedProcess(1)})
        before = TaskcardStore("M8", repo_root=tmp_path).path.read_text(encoding="utf-8")
        main(["--mission", "M8", "--repo-root", str(tmp_path)], runner=runner)
        after = TaskcardStore("M8", repo_root=tmp_path).path.read_text(encoding="utf-8")
        assert before == after
