from types import SimpleNamespace

from scripts.ci.checks import check_grade_churn
from scripts.pipeline.commands.governance import check_graded_at_only


def _completed(stdout="", returncode=0):
    return SimpleNamespace(stdout=stdout, stderr="", returncode=returncode)


def test_grade_churn_detects_grade_only(monkeypatch):
    def fake_run(cmd, **kwargs):
        if "--name-only" in cmd:
            return _completed("content/a.md\ncontent/b.md\n")
        return _completed("@@\n-grade: C\n+grade: B\n-graded_content_hash: old\n+graded_content_hash: new\n")

    monkeypatch.setattr(check_grade_churn.subprocess, "run", fake_run)

    assert check_grade_churn.main(["--block-threshold", "2"]) == 1


def test_grade_churn_allows_annotation(monkeypatch):
    monkeypatch.setattr(check_grade_churn.subprocess, "run", lambda *args, **kwargs: _completed("content/a.md\n"))

    assert check_grade_churn.main(["--commit-msg", "BULK-GRADE-MIGRATION: approved by tester"]) == 0


def test_grade_churn_body_change_not_grade_only(monkeypatch):
    def fake_run(cmd, **kwargs):
        if "--name-only" in cmd:
            return _completed("content/a.md\n")
        return _completed("@@\n-grade: C\n+grade: B\n-old body\n+new body\n")

    monkeypatch.setattr(check_grade_churn.subprocess, "run", fake_run)

    assert check_grade_churn.main(["--block-threshold", "1"]) == 0


def test_check_graded_at_only_prints_only_case_a(tmp_path, monkeypatch, capsys):
    files = tmp_path / "files.txt"
    files.write_text("content/a.md\ncontent/b.md\n", encoding="utf-8")

    def fake_run(cmd, **kwargs):
        path = cmd[-1]
        if path.endswith("a.md"):
            return _completed("@@\n-graded_at: old\n+graded_at: new\n")
        return _completed("@@\n-graded_at: old\n+graded_at: new\n-title: A\n+title: B\n")

    monkeypatch.setattr(check_graded_at_only.subprocess, "run", fake_run)

    assert check_graded_at_only.main(["--files-from", str(files), "--mode", "worktree"]) == 0
    assert capsys.readouterr().out.strip() == "content/a.md"


def test_check_graded_at_only_parse_failure(tmp_path, monkeypatch, capsys):
    files = tmp_path / "files.txt"
    files.write_text("content/a.md\n", encoding="utf-8")
    monkeypatch.setattr(check_graded_at_only.subprocess, "run", lambda *args, **kwargs: _completed(returncode=1))

    assert check_graded_at_only.main(["--files-from", str(files)]) == 2
    assert "PARSE_FAILURE:content/a.md" in capsys.readouterr().err
