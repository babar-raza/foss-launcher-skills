"""Tests for commands/ops/st054_campaign_worker.py (ST-054 TC-19,
plans/from_backlog/2026-08-16-st-054-inline-install-command-remediation.md).
"""
import json
import subprocess
import sys
from pathlib import Path

import pytest

_PIPELINE_ROOT = Path(__file__).resolve().parents[1]
if str(_PIPELINE_ROOT) not in sys.path:
    sys.path.insert(0, str(_PIPELINE_ROOT))

import commands.ops.st054_campaign_worker as sut  # noqa: E402
import commands.ops.st054_seed_taskcards as seeder  # noqa: E402
from taskcard_store import TaskcardStore  # noqa: E402


_NUGET_REGISTRY = {
    "words": {"net": {
        "registry_type": "nuget", "candidate": {"name": "Aspose.Words.FOSS"},
        "verification": {"published": True},
    }},
}


def _write_registry(tmp_path: Path, data: dict) -> None:
    (tmp_path / "data").mkdir(parents=True, exist_ok=True)
    (tmp_path / "data" / "package_registry.json").write_text(json.dumps(data), encoding="utf-8")


def _write(tmp_path: Path, rel_path: str, content: str) -> Path:
    p = tmp_path / rel_path
    p.parent.mkdir(parents=True, exist_ok=True)
    p.write_text(content, encoding="utf-8")
    return p


@pytest.fixture(autouse=True)
def isolate_repo(tmp_path):
    sut.configure(repo_root=tmp_path)
    seeder.configure(repo_root=tmp_path)
    yield
    sut.configure(repo_root=None)
    seeder.configure(repo_root=None)


class TestStepFunctions:
    def test_block_migrate_dry_run_finds_but_does_not_write(self, tmp_path):
        _write_registry(tmp_path, _NUGET_REGISTRY)
        p = _write(
            tmp_path, "content/docs.aspose.org/en/words/net/getting-started/installation.md",
            "Install:\n\n```bash\ndotnet add package Aspose.Words.FOSS\n```\n",
        )
        result = sut._step_block_migrate("words", "net", dry_run=True)
        assert result["ok"] is True
        assert "files_migrated=1" in result["detail"]
        assert "dotnet add package" in p.read_text(encoding="utf-8")  # unchanged

    def test_block_migrate_execute_writes_shortcode(self, tmp_path):
        _write_registry(tmp_path, _NUGET_REGISTRY)
        p = _write(
            tmp_path, "content/docs.aspose.org/en/words/net/getting-started/installation.md",
            "Install:\n\n```bash\ndotnet add package Aspose.Words.FOSS\n```\n",
        )
        result = sut._step_block_migrate("words", "net", dry_run=False)
        assert result["ok"] is True
        assert result["modified_files"]
        assert 'package-install "words" "net"' in p.read_text(encoding="utf-8")

    def test_block_migrate_covers_locale_files_not_just_english(self, tmp_path):
        """The whole point of dropping the separate locale_patch step --
        block_migrator.discover_files() must reach locale copies directly."""
        _write_registry(tmp_path, _NUGET_REGISTRY)
        _write(
            tmp_path, "content/docs.aspose.org/en/words/net/getting-started/installation.md",
            "```bash\ndotnet add package Aspose.Words.FOSS\n```\n",
        )
        de_page = _write(
            tmp_path, "content/docs.aspose.org/de/words/net/getting-started/installation.md",
            "```bash\ndotnet add package Aspose.Words.FOSS\n```\n",
        )
        result = sut._step_block_migrate("words", "net", dry_run=False)
        assert result["ok"] is True
        assert len(result["modified_files"]) == 2
        assert 'package-install "words" "net"' in de_page.read_text(encoding="utf-8")

    def test_inline_migrate_execute_writes_inline_shortcode_including_locales(self, tmp_path):
        _write_registry(tmp_path, _NUGET_REGISTRY)
        en = _write(
            tmp_path, "content/docs.aspose.org/en/words/net/faq.md",
            "Run `dotnet add package Aspose.Words.FOSS` to install it.\n",
        )
        de = _write(
            tmp_path, "content/docs.aspose.org/de/words/net/faq.md",
            "Run `dotnet add package Aspose.Words.FOSS` to install it.\n",
        )
        result = sut._step_inline_migrate("words", "net", dry_run=False)
        assert result["ok"] is True
        assert len(result["modified_files"]) == 2
        assert 'package-install-inline "words" "net"' in en.read_text(encoding="utf-8")
        assert 'package-install-inline "words" "net"' in de.read_text(encoding="utf-8")

    def test_verify_reports_zero_after_migration(self, tmp_path):
        _write_registry(tmp_path, _NUGET_REGISTRY)
        _write(
            tmp_path, "content/docs.aspose.org/en/words/net/getting-started/installation.md",
            '{{< package-install "words" "net" >}}\n',
        )
        result = sut._step_verify("words", "net")
        assert result["ok"] is True
        assert result["findings"] == 0

    def test_verify_reports_nonzero_before_migration(self, tmp_path):
        _write_registry(tmp_path, _NUGET_REGISTRY)
        _write(
            tmp_path, "content/docs.aspose.org/en/words/net/getting-started/installation.md",
            "dotnet add package Aspose.Words.FOSS\n",
        )
        result = sut._step_verify("words", "net")
        assert result["ok"] is True
        assert result["findings"] == 1

    def test_step_commit_with_no_modified_files_is_a_noop(self, tmp_path):
        result = sut._step_commit("words", "net", [], skills=["S-118"], plan="some-plan.md")
        assert result["ok"] is True
        assert result["commit_sha"] is None

    def test_step_commit_invokes_git_plumb_commit_and_parses_sha(self, tmp_path, monkeypatch):
        calls = []

        def fake_run(cmd, **kwargs):
            calls.append(cmd)
            if "git_plumb_commit.py" in cmd[1]:
                return subprocess.CompletedProcess(cmd, 0, stdout="commit_sha=abc123\npushed=True\n", stderr="")
            return subprocess.CompletedProcess(cmd, 0, stdout="", stderr="")

        monkeypatch.setattr(sut.subprocess, "run", fake_run)
        result = sut._step_commit("words", "net", ["content/x.md"], skills=["S-118"], plan="some-plan.md")
        assert result["ok"] is True
        assert result["commit_sha"] == "abc123"
        assert "--files" in calls[0]

    def test_step_commit_reports_failure_when_plumb_commit_fails(self, tmp_path, monkeypatch):
        def fake_run(cmd, **kwargs):
            return subprocess.CompletedProcess(cmd, 2, stdout="ERROR: something failed\n", stderr="")

        monkeypatch.setattr(sut.subprocess, "run", fake_run)
        result = sut._step_commit("words", "net", ["content/x.md"], skills=["S-118"], plan="some-plan.md")
        assert result["ok"] is False
        assert result["commit_sha"] is None

    def test_step_commit_uses_files_from_for_large_batches(self, tmp_path, monkeypatch):
        calls = []

        def fake_run(cmd, **kwargs):
            calls.append(cmd)
            if "git_plumb_commit.py" in cmd[1]:
                return subprocess.CompletedProcess(cmd, 0, stdout="commit_sha=deadbeef\n", stderr="")
            return subprocess.CompletedProcess(cmd, 0, stdout="", stderr="")

        monkeypatch.setattr(sut.subprocess, "run", fake_run)
        (tmp_path / "reports").mkdir(parents=True, exist_ok=True)
        many_files = [f"content/docs.aspose.org/en/words/net/page{i}.md" for i in range(401)]
        result = sut._step_commit("words", "net", many_files, skills=["S-118"], plan="some-plan.md")
        assert result["ok"] is True
        assert "--files-from" in calls[0]


class TestProcessOneStepOverRealTaskcardCli:
    """Real subprocess integration against the actual taskcard_cli.py, not
    mocked -- exercises the real CAS/ready/claim/advance contract this
    module deliberately reuses instead of reimplementing."""

    def test_full_product_pipeline_advances_through_all_four_steps(self, tmp_path, monkeypatch):
        _write_registry(tmp_path, _NUGET_REGISTRY)
        _write(
            tmp_path, "content/docs.aspose.org/en/words/net/getting-started/installation.md",
            "```bash\ndotnet add package Aspose.Words.FOSS\n```\n",
        )
        seeder.seed_products([("words", "net")], recorded_by="test")

        real_run = subprocess.run

        def selective_fake_run(cmd, **kwargs):
            if "git_plumb_commit.py" in cmd[1]:
                return subprocess.CompletedProcess(cmd, 0, stdout="commit_sha=fakeshaforthistest\n", stderr="")
            return real_run(cmd, **kwargs)

        monkeypatch.setattr(sut.subprocess, "run", selective_fake_run)

        results = sut.process_product(
            "words", "net", run_id="test-run-1", session_id="test-session-1", max_steps=6,
        )
        steps_seen = [r["step"] for r in results]
        assert steps_seen == ["block_migrate", "inline_migrate", "verify", "commit"]
        assert all(r["outcome"] == "CLOSED" for r in results)
        # commit had nothing further to do beyond block_migrate's own write
        # (no separate inline mention left after the block replacement).
        store = TaskcardStore(seeder.DEFAULT_MISSION_ID, repo_root=tmp_path)
        latest = store.read_latest()
        assert latest["TC-words-net-verify"]["status"] == "CLOSED"

    def test_nothing_ready_returns_empty_list(self, tmp_path):
        _write_registry(tmp_path, _NUGET_REGISTRY)
        results = sut.process_product("words", "net", run_id="r1", session_id="s1")
        assert results == []

    def test_once_flag_stops_after_a_single_step(self, tmp_path):
        _write_registry(tmp_path, _NUGET_REGISTRY)
        _write(
            tmp_path, "content/docs.aspose.org/en/words/net/getting-started/installation.md",
            "```bash\ndotnet add package Aspose.Words.FOSS\n```\n",
        )
        seeder.seed_products([("words", "net")], recorded_by="test")
        results = sut.process_product(
            "words", "net", run_id="r1", session_id="s1", once=True,
        )
        assert len(results) == 1
        assert results[0]["step"] == "block_migrate"

    def test_needs_manual_review_blocks_commit_until_confirmed(self, tmp_path):
        _write_registry(tmp_path, {
            "cells": {"net": {"registry_type": "nuget", "candidate": {"name": "Aspose.Cells.FOSS"},
                                "verification": {"published": True}}},
        })
        seeder.seed_products(
            [("cells", "net")], needs_manual_review_products={("cells", "net")}, recorded_by="test",
        )
        results = sut.process_product("cells", "net", run_id="r1", session_id="s1", max_steps=6)
        assert results[-1]["outcome"] == "AWAITING_MANUAL_REVIEW"
        store = TaskcardStore(seeder.DEFAULT_MISSION_ID, repo_root=tmp_path)
        # commit taskcard must still be TODO -- never silently claimed/advanced.
        assert store.read_latest()["TC-cells-net-commit"]["status"] == "TODO"

    def test_needs_manual_review_proceeds_with_confirm_flag(self, tmp_path, monkeypatch):
        _write_registry(tmp_path, {
            "cells": {"net": {"registry_type": "nuget", "candidate": {"name": "Aspose.Cells.FOSS"},
                                "verification": {"published": True}}},
        })
        seeder.seed_products(
            [("cells", "net")], needs_manual_review_products={("cells", "net")}, recorded_by="test",
        )

        real_run = subprocess.run

        def selective_fake_run(cmd, **kwargs):
            if "git_plumb_commit.py" in cmd[1]:
                return subprocess.CompletedProcess(cmd, 0, stdout="commit_sha=cafef00d\n", stderr="")
            return real_run(cmd, **kwargs)

        monkeypatch.setattr(sut.subprocess, "run", selective_fake_run)
        results = sut.process_product(
            "cells", "net", run_id="r1", session_id="s1", max_steps=6, confirm_manual_review=True,
        )
        assert results[-1]["outcome"] == "CLOSED"
        assert results[-1]["step"] == "commit"

    def test_verify_failure_blocks_and_does_not_cascade_to_commit(self, tmp_path):
        """No registry entry for the product -> verify's own ok=False path;
        commit must never become eligible since verify never reaches CLOSED."""
        _write_registry(tmp_path, {})  # words/net not registered at all
        seeder.seed_products([("words", "net")], recorded_by="test")
        results = sut.process_product("words", "net", run_id="r1", session_id="s1", max_steps=6)
        assert any(r["outcome"] == "BLOCKED_LOCAL" for r in results)
        assert not any(r["step"] == "commit" for r in results)


def test_collect_modified_files_reads_prior_step_evidence(tmp_path):
    store = TaskcardStore(seeder.DEFAULT_MISSION_ID, repo_root=tmp_path)
    store.append({
        "task_id": "TC-words-net-block_migrate", "status": "TODO",
        "recorded_at": "2026-01-01T00:00:00Z", "recorded_by": "s", "evidence_refs": [],
    })
    store.update_taskcard_status(
        "TC-words-net-block_migrate", expected_status="TODO", new_status="CLOSED",
        recorded_by="s", evidence_refs=["content/a.md", "content/b.md"],
    )
    store.append({
        "task_id": "TC-words-net-inline_migrate", "status": "TODO",
        "recorded_at": "2026-01-01T00:00:00Z", "recorded_by": "s", "evidence_refs": [],
    })
    store.update_taskcard_status(
        "TC-words-net-inline_migrate", expected_status="TODO", new_status="CLOSED",
        recorded_by="s", evidence_refs=["content/b.md", "content/c.md"],
    )
    files = sut._collect_modified_files(seeder.DEFAULT_MISSION_ID, "words", "net")
    assert files == ["content/a.md", "content/b.md", "content/c.md"]  # de-duped, order preserved


def test_main_reports_success_exit_code(tmp_path, capsys):
    _write_registry(tmp_path, _NUGET_REGISTRY)
    exit_code = sut.main(["--product", "words/net", "--run-id", "cli-test"])
    assert exit_code == 0
    assert "nothing ready" in capsys.readouterr().out


def test_main_requires_slash_in_product():
    with pytest.raises(SystemExit):
        sut.main(["--product", "wordsnet", "--run-id", "x"])


def test_module_is_importable_via_real_subprocess_m_invocation():
    """Regression pin: an earlier version imported
    `from st054_seed_taskcards import ...` (bare top-level name) instead of
    `from commands.ops.st054_seed_taskcards import ...` -- this passed every
    in-process `import commands.ops.st054_campaign_worker as sut` test in
    this file (pytest's own sys.path setup happened to make the bare name
    resolvable) but crashed immediately on the real
    `-m commands.ops.st054_campaign_worker` CLI invocation operators
    actually use, with no test catching it. This test exercises the exact
    real invocation path instead of the in-process import."""
    env = dict(__import__("os").environ, PYTHONPATH=str(_PIPELINE_ROOT))
    result = subprocess.run(
        [sys.executable, "-m", "commands.ops.st054_campaign_worker", "--help"],
        cwd=str(_PIPELINE_ROOT), capture_output=True, text=True,
        encoding="utf-8", errors="replace", env=env, timeout=30,
    )
    assert result.returncode == 0, f"stderr: {result.stderr}"
    assert "--product" in result.stdout
