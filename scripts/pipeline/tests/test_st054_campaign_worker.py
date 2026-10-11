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


class TestFrontmatterSafety:
    """Regression coverage for a real content-corruption bug caught live
    during the TC-20 pilot: 36 products.aspose.org/note/python pages had a
    `pip install` mention inside a YAML `faq.answer` frontmatter field.
    Hugo shortcodes never render inside frontmatter data values (only body
    markdown) -- the unwrapped migrator broke YAML on one locale outright
    (caught by the Tier-1 pre-commit gate) and would have landed
    non-functional literal shortcode text on the other 35."""

    def test_split_frontmatter_separates_delimiters_from_body(self):
        text = '---\ntitle: X\nfaq:\n  - answer: "run `pip install x`"\n---\nBody `pip install x` here.\n'
        fm, body = sut._split_frontmatter(text)
        assert fm == '---\ntitle: X\nfaq:\n  - answer: "run `pip install x`"\n---\n'
        assert body == "Body `pip install x` here.\n"

    def test_split_frontmatter_no_frontmatter_returns_empty(self):
        text = "Just body `pip install x` text.\n"
        fm, body = sut._split_frontmatter(text)
        assert fm == ""
        assert body == text

    def test_inline_migrate_does_not_touch_frontmatter_faq_answer(self, tmp_path):
        _write_registry(tmp_path, {
            "note": {"python": {"registry_type": "pypi", "candidate": {"name": "aspose-note"},
                                  "verification": {"published": True}}},
        })
        page = _write(
            tmp_path, "content/products.aspose.org/tr/note/python/_index.md",
            '---\n'
            'title: "Aspose.Note"\n'
            'faq:\n'
            '  - question: "Nasil?"\n'
            '    answer: "`pip install aspose-note`\'i calistirin."\n'
            '---\n'
            '\n'
            'Body text: `pip install aspose-note` here.\n',
        )
        result = sut._step_inline_migrate("note", "python", dry_run=False)
        assert result["ok"] is True
        content = page.read_text(encoding="utf-8")
        # Frontmatter's backtick command must survive untouched...
        assert '`pip install aspose-note`\'i calistirin' in content
        # ...while the body mention IS migrated.
        assert 'package-install-inline "note" "python"' in content
        body_part = content.split("---\n", 2)[2]
        assert "package-install-inline" in body_part
        fm_part = content.split("---\n", 2)[1]
        assert "package-install-inline" not in fm_part

    def test_inline_migrate_preview_reports_frontmatter_file_without_writing(self, tmp_path):
        _write_registry(tmp_path, {
            "note": {"python": {"registry_type": "pypi", "candidate": {"name": "aspose-note"},
                                  "verification": {"published": True}}},
        })
        original = (
            '---\n'
            'faq:\n'
            '  - answer: "`pip install aspose-note`"\n'
            '---\n'
            '\n'
            'Body: `pip install aspose-note`\n'
        )
        page = _write(tmp_path, "content/products.aspose.org/tr/note/python/_index.md", original)
        result = sut._step_inline_migrate("note", "python", dry_run=True)
        assert result["ok"] is True
        assert page.read_text(encoding="utf-8") == original  # untouched in dry-run

    def test_block_migrate_does_not_touch_frontmatter_fenced_block(self, tmp_path):
        """Same protection for the block-level migrator -- a YAML literal
        block scalar containing a fenced-code-shaped install command must
        not be touched."""
        _write_registry(tmp_path, {
            "words": {"net": {"registry_type": "nuget", "candidate": {"name": "Aspose.Words.FOSS"},
                                "verification": {"published": True}}},
        })
        page = _write(
            tmp_path, "content/docs.aspose.org/en/words/net/getting-started/installation.md",
            '---\n'
            'title: "Install"\n'
            'note: |\n'
            '  ```bash\n'
            '  dotnet add package Aspose.Words.FOSS\n'
            '  ```\n'
            '---\n'
            '\n'
            '```bash\n'
            'dotnet add package Aspose.Words.FOSS\n'
            '```\n',
        )
        result = sut._step_block_migrate("words", "net", dry_run=False)
        assert result["ok"] is True
        content = page.read_text(encoding="utf-8")
        fm_part, body_part = content.split("---\n", 2)[1], content.split("---\n", 2)[2]
        assert "dotnet add package" in fm_part  # untouched
        assert "package-install" in body_part  # migrated

    def test_no_frontmatter_file_behaves_exactly_as_before(self, tmp_path):
        """Files with no frontmatter at all must go through migrate_file()
        directly, unchanged behavior from before this wrapper existed."""
        _write_registry(tmp_path, _NUGET_REGISTRY)
        page = _write(
            tmp_path, "content/blog.aspose.org/words/net/post/index.md",
            "Run `dotnet add package Aspose.Words.FOSS` to install it.\n",
        )
        result = sut._step_inline_migrate("words", "net", dry_run=False)
        assert result["ok"] is True
        assert 'package-install-inline "words" "net"' in page.read_text(encoding="utf-8")


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


class TestPreviewNextStep:
    """Regression coverage for the exact bug the TC-20 pilot itself caught
    live: a preview must never claim or advance the taskcard, regardless of
    what it finds."""

    def test_preview_does_not_mutate_taskcard_state(self, tmp_path):
        _write_registry(tmp_path, _NUGET_REGISTRY)
        _write(
            tmp_path, "content/docs.aspose.org/en/words/net/getting-started/installation.md",
            "```bash\ndotnet add package Aspose.Words.FOSS\n```\n",
        )
        seeder.seed_products([("words", "net")], recorded_by="test")

        preview = sut.preview_next_step("words", "net", session_id="s1")
        assert preview is not None
        assert preview["step"] == "block_migrate"
        assert "files_migrated=1" in preview["detail"]

        store = TaskcardStore(seeder.DEFAULT_MISSION_ID, repo_root=tmp_path)
        assert store.read_latest()["TC-words-net-block_migrate"]["status"] == "TODO"
        # And the file itself must be untouched -- preview is dry-run underneath.
        page = tmp_path / "content/docs.aspose.org/en/words/net/getting-started/installation.md"
        assert "dotnet add package" in page.read_text(encoding="utf-8")

    def test_preview_returns_none_when_nothing_ready(self, tmp_path):
        _write_registry(tmp_path, _NUGET_REGISTRY)
        assert sut.preview_next_step("words", "net", session_id="s1") is None

    def test_preview_has_no_form_for_verify_or_commit(self, tmp_path):
        _write_registry(tmp_path, _NUGET_REGISTRY)
        seeder.seed_products([("words", "net")], recorded_by="test")
        # Manually advance block_migrate + inline_migrate to CLOSED so verify is next.
        store = TaskcardStore(seeder.DEFAULT_MISSION_ID, repo_root=tmp_path)
        for step in ("block_migrate", "inline_migrate"):
            store.update_taskcard_status(
                f"TC-words-net-{step}", expected_status="TODO", new_status="CLOSED",
                recorded_by="s1", evidence_refs=["no-op"],
            )
        preview = sut.preview_next_step("words", "net", session_id="s1")
        assert preview["step"] == "verify"
        assert "no dry-run preview form" in preview["detail"]

    def test_main_preview_flag_prints_and_does_not_mutate(self, tmp_path, capsys):
        _write_registry(tmp_path, _NUGET_REGISTRY)
        _write(
            tmp_path, "content/docs.aspose.org/en/words/net/getting-started/installation.md",
            "```bash\ndotnet add package Aspose.Words.FOSS\n```\n",
        )
        seeder.seed_products([("words", "net")], recorded_by="test")
        exit_code = sut.main(["--product", "words/net", "--run-id", "r1", "--preview"])
        assert exit_code == 0
        assert "PREVIEW ONLY, taskcard untouched" in capsys.readouterr().out
        store = TaskcardStore(seeder.DEFAULT_MISSION_ID, repo_root=tmp_path)
        assert store.read_latest()["TC-words-net-block_migrate"]["status"] == "TODO"


class TestLargeBatchEvidence:
    """Regression coverage for a real crash caught live during the TC-20
    pilot: taskcard_cli.py advance passes evidence as individual --evidence
    CLI args, and note/python's inline_migrate step modified 425 files --
    well past Windows' command-line length limit (WinError 206). The real
    file writes had already succeeded; only the taskcard advance crashed,
    leaving it stuck IN_PROGRESS with the work done but unrecorded."""

    def test_build_evidence_refs_inlines_small_lists(self, tmp_path):
        refs = sut._build_evidence_refs("ST-054-REMEDIATION", "TC-x", ["a.md", "b.md"])
        assert refs == ["a.md", "b.md"]
        assert not (tmp_path / "reports" / "plan_state").exists()

    def test_build_evidence_refs_writes_a_file_for_large_lists(self, tmp_path):
        files = [f"content/f{i}.md" for i in range(425)]
        refs = sut._build_evidence_refs("ST-054-REMEDIATION", "TC-note-python-inline_migrate", files)
        assert len(refs) == 2  # short regardless of how many real files
        assert refs[0].startswith(sut._EVIDENCE_FILE_PREFIX)
        assert refs[1] == "count=425"
        evidence_path = tmp_path / "reports" / "plan_state" / "ST-054-REMEDIATION" / "evidence" / "TC-note-python-inline_migrate.json"
        assert evidence_path.is_file()
        assert json.loads(evidence_path.read_text(encoding="utf-8"))["modified_files"] == files

    def test_resolve_evidence_files_round_trips_large_batches(self, tmp_path):
        files = [f"content/f{i}.md" for i in range(425)]
        refs = sut._build_evidence_refs("ST-054-REMEDIATION", "TC-x", files)
        assert sut._resolve_evidence_files(refs) == files

    def test_resolve_evidence_files_passes_through_literal_paths(self, tmp_path):
        assert sut._resolve_evidence_files(["content/a.md", "content/b.md"]) == ["content/a.md", "content/b.md"]

    def test_resolve_evidence_files_drops_non_path_markers(self, tmp_path):
        assert sut._resolve_evidence_files(["findings=0", "count=5"]) == []

    def test_full_pipeline_survives_a_large_modified_file_set(self, tmp_path, monkeypatch):
        """End-to-end: seed a product, monkeypatch the block_migrate step to
        report a large (421-file) modified set without actually writing 421
        real files to disk, and confirm the taskcard advances to CLOSED
        instead of crashing -- the exact failure mode this fix closes."""
        _write_registry(tmp_path, _NUGET_REGISTRY)
        seeder.seed_products([("words", "net")], recorded_by="test")

        many_files = [f"content/docs.aspose.org/{loc}/words/net/page.md" for loc in range(421)]

        def fake_block_migrate(family, platform, *, dry_run):
            return {"ok": True, "modified_files": many_files, "detail": "files_migrated=421 (synthetic)"}

        monkeypatch.setitem(sut._STEP_FUNCS, "block_migrate", fake_block_migrate)

        result = sut.process_one_step("words", "net", run_id="r1", session_id="s1")
        assert result["outcome"] == "CLOSED"

        store = TaskcardStore(seeder.DEFAULT_MISSION_ID, repo_root=tmp_path)
        row = store.read_latest()["TC-words-net-block_migrate"]
        assert any(ref.startswith(sut._EVIDENCE_FILE_PREFIX) for ref in row["evidence_refs"])

        # And _collect_modified_files must still see the full 421 files for
        # the eventual commit step, not just the short pointer.
        collected = sut._collect_modified_files(seeder.DEFAULT_MISSION_ID, "words", "net")
        assert len(collected) == 421


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
