"""SEO-SCHEMA-A-WORKFLOW-UPDATE Migration Plan v2: tests for the automatic,
state-tracked platform-label migration (migrate_platform_labels.py).

Companion to test_get_keywords_change_detection.py's Finding #52 tests --
those prove replace_keywords_for_entry() itself is correct; these prove the
orchestration around it (state persistence, resumability, budget, circuit
breaker) actually uses it correctly across real (simulated) weekly runs.
"""
from __future__ import annotations

import json
import sys
from pathlib import Path

import pytest

_SCRIPTS = Path(__file__).resolve().parents[2]
_PIPELINE = _SCRIPTS / "pipeline"
_SEO = _SCRIPTS / "seo"
if str(_SCRIPTS) not in sys.path:
    sys.path.insert(0, str(_SCRIPTS))
if str(_PIPELINE) not in sys.path:
    sys.path.insert(0, str(_PIPELINE))
if str(_SEO) not in sys.path:
    sys.path.insert(0, str(_SEO))

import get_keywords  # noqa: E402
import migrate_platform_labels as migrate  # noqa: E402


def _write_md(path: Path, title: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(f"---\ntitle: {title}\n---\nBody\n", encoding="utf-8")


def _write_family_json(output_dir: Path, family: str, entries: list[dict]) -> None:
    (output_dir / f"{family}.json").write_text(json.dumps(entries), encoding="utf-8")


class TestStateFileIO:
    def test_load_missing_state_returns_fresh_structure(self, tmp_path):
        state = migrate.load_migration_state(tmp_path / "does_not_exist.json")
        assert state["families"] == {}
        assert state["migration_complete"] is False
        assert set(state["target_families"]) == set(migrate.TARGET_FAMILIES)

    def test_save_then_load_roundtrips(self, tmp_path):
        state_path = tmp_path / "state.json"
        state = {"target_families": ["tex"], "families": {"tex": {"status": "done"}}, "migration_complete": True}
        migrate.save_migration_state_atomic(state_path, state)
        loaded = migrate.load_migration_state(state_path)
        assert loaded == state

    def test_atomic_write_failure_leaves_previous_state_intact(self, tmp_path, monkeypatch):
        state_path = tmp_path / "state.json"
        original = {"target_families": ["tex"], "families": {}, "migration_complete": False}
        migrate.save_migration_state_atomic(state_path, original)

        def _boom(*a, **kw):
            raise OSError("simulated crash during os.replace")

        monkeypatch.setattr(migrate.os, "replace", _boom)
        with pytest.raises(OSError):
            migrate.save_migration_state_atomic(state_path, {"target_families": [], "families": {"x": 1}, "migration_complete": True})

        # Original file must be untouched -- no partial/corrupt write landed.
        reloaded = migrate.load_migration_state(state_path)
        assert reloaded == original


class TestMigrateFamilies:
    def test_skips_already_migrated_source_paths(self, tmp_path, monkeypatch):
        monkeypatch.setattr(migrate, "_REPO_ROOT", tmp_path)
        site = tmp_path / "content" / "kb.aspose.org" / "en"
        _write_md(site / "tex" / "page.md", "Some Title")
        output_dir = tmp_path / "keywords"
        output_dir.mkdir()
        source_path = Path(site / "tex" / "page.md").resolve().relative_to(tmp_path).as_posix()
        _write_family_json(output_dir, "tex", [{"pageTitle": "Some Title", "sourcePath": source_path, "keywords": ["wrong"]}])

        state_path = tmp_path / "state.json"
        migrate.save_migration_state_atomic(state_path, {
            "target_families": ["tex"],
            "families": {"tex": {"status": "in_progress", "migrated_source_paths": [source_path]}},
            "migration_complete": False,
        })

        call_count = {"n": 0}
        monkeypatch.setattr(get_keywords, "get_keywords_from_gemini", lambda title, platform="net": (call_count.__setitem__("n", call_count["n"] + 1), ["new"])[1])

        migrate.migrate_families(["tex"], [str(site)], str(output_dir), state_path=state_path)
        assert call_count["n"] == 0

    def test_migrates_and_replaces_keywords_for_pending_file(self, tmp_path, monkeypatch):
        monkeypatch.setattr(migrate, "_REPO_ROOT", tmp_path)
        site = tmp_path / "content" / "kb.aspose.org" / "en"
        _write_md(site / "tex" / "net" / "page.md", "Some Title")
        output_dir = tmp_path / "keywords"
        output_dir.mkdir()
        source_path = Path(site / "tex" / "net" / "page.md").resolve().relative_to(tmp_path).as_posix()
        _write_family_json(output_dir, "tex", [{"pageTitle": "Some Title", "sourcePath": source_path, "keywords": ["wrong-platform"]}])

        monkeypatch.setattr(get_keywords, "get_keywords_from_gemini", lambda title, platform="net": ["correct"])

        state_path = tmp_path / "state.json"
        state = migrate.migrate_families(["tex"], [str(site)], str(output_dir), state_path=state_path)

        data = json.loads((output_dir / "tex.json").read_text(encoding="utf-8"))
        assert data[0]["keywords"] == ["correct"], "old wrong-platform keywords must be replaced, not unioned"
        assert source_path in state["families"]["tex"].get("migrated_source_paths", []) or state["families"]["tex"]["status"] == "done"

    def test_family_flips_to_done_when_fully_migrated(self, tmp_path, monkeypatch):
        monkeypatch.setattr(migrate, "_REPO_ROOT", tmp_path)
        site = tmp_path / "content" / "kb.aspose.org" / "en"
        _write_md(site / "tex" / "page.md", "Only Page")
        output_dir = tmp_path / "keywords"
        output_dir.mkdir()
        source_path = Path(site / "tex" / "page.md").resolve().relative_to(tmp_path).as_posix()
        _write_family_json(output_dir, "tex", [{"pageTitle": "Only Page", "sourcePath": source_path, "keywords": ["wrong"]}])

        monkeypatch.setattr(get_keywords, "get_keywords_from_gemini", lambda title, platform="net": ["correct"])

        state_path = tmp_path / "state.json"
        state = migrate.migrate_families(["tex"], [str(site)], str(output_dir), state_path=state_path)

        assert state["families"]["tex"]["status"] == "done"
        assert state["migration_complete"] is True

        # A second run must make zero further calls -- the family is done.
        call_count = {"n": 0}

        def _fake(title, platform="net"):
            call_count["n"] += 1
            return ["correct-again"]

        monkeypatch.setattr(get_keywords, "get_keywords_from_gemini", _fake)
        migrate.migrate_families(["tex"], [str(site)], str(output_dir), state_path=state_path)
        assert call_count["n"] == 0

    def test_respects_max_calls_budget_and_exits_cleanly(self, tmp_path, monkeypatch):
        monkeypatch.setattr(migrate, "_REPO_ROOT", tmp_path)
        site = tmp_path / "content" / "kb.aspose.org" / "en"
        output_dir = tmp_path / "keywords"
        output_dir.mkdir()
        entries = []
        for i in range(10):
            _write_md(site / "tex" / f"page{i}.md", f"Title {i}")
            sp = Path(site / "tex" / f"page{i}.md").resolve().relative_to(tmp_path).as_posix()
            entries.append({"pageTitle": f"Title {i}", "sourcePath": sp, "keywords": ["wrong"]})
        _write_family_json(output_dir, "tex", entries)

        monkeypatch.setattr(get_keywords, "get_keywords_from_gemini", lambda title, platform="net": ["correct"])

        state_path = tmp_path / "state.json"
        # Must return normally, not raise SystemExit.
        state = migrate.migrate_families(["tex"], [str(site)], str(output_dir), state_path=state_path, max_calls=4)

        assert len(state["families"]["tex"]["migrated_source_paths"]) == 4
        assert state["families"]["tex"]["status"] == "in_progress"
        assert state["migration_complete"] is False

    def test_circuit_breaker_trips_and_raises_systemexit_with_progress_saved(self, tmp_path, monkeypatch):
        monkeypatch.setattr(migrate, "_REPO_ROOT", tmp_path)
        site = tmp_path / "content" / "kb.aspose.org" / "en"
        output_dir = tmp_path / "keywords"
        output_dir.mkdir()
        entries = []
        for i in range(6):
            _write_md(site / "tex" / f"page{i}.md", f"Title {i}")
            sp = Path(site / "tex" / f"page{i}.md").resolve().relative_to(tmp_path).as_posix()
            entries.append({"pageTitle": f"Title {i}", "sourcePath": sp, "keywords": ["wrong"]})
        _write_family_json(output_dir, "tex", entries)

        call_count = {"n": 0}

        def _always_fail(title, platform="net"):
            call_count["n"] += 1
            return None

        monkeypatch.setattr(get_keywords, "get_keywords_from_gemini", _always_fail)

        state_path = tmp_path / "state.json"
        with pytest.raises(SystemExit):
            migrate.migrate_families(["tex"], [str(site)], str(output_dir), state_path=state_path)

        assert call_count["n"] == get_keywords._CIRCUIT_BREAKER_CONSECUTIVE_FAILURES
        # State was still saved before the SystemExit -- resumable.
        saved = migrate.load_migration_state(state_path)
        assert "tex" in saved["families"]

    def test_all_calls_failing_raises_systemexit(self, tmp_path, monkeypatch):
        monkeypatch.setattr(migrate, "_REPO_ROOT", tmp_path)
        site = tmp_path / "content" / "kb.aspose.org" / "en"
        output_dir = tmp_path / "keywords"
        output_dir.mkdir()
        _write_md(site / "tex" / "page.md", "Title")
        sp = Path(site / "tex" / "page.md").resolve().relative_to(tmp_path).as_posix()
        _write_family_json(output_dir, "tex", [{"pageTitle": "Title", "sourcePath": sp, "keywords": ["wrong"]}])

        monkeypatch.setattr(get_keywords, "get_keywords_from_gemini", lambda title, platform="net": None)

        state_path = tmp_path / "state.json"
        with pytest.raises(SystemExit):
            migrate.migrate_families(["tex"], [str(site)], str(output_dir), state_path=state_path)

    def test_scans_across_multiple_content_sites(self, tmp_path, monkeypatch):
        monkeypatch.setattr(migrate, "_REPO_ROOT", tmp_path)
        kb_site = tmp_path / "content" / "kb.aspose.org" / "en"
        docs_site = tmp_path / "content" / "docs.aspose.org" / "en"
        _write_md(kb_site / "tex" / "faq.md", "FAQ Title")
        _write_md(docs_site / "tex" / "net" / "quickstart.md", "Quickstart Title")
        output_dir = tmp_path / "keywords"
        output_dir.mkdir()
        _write_family_json(output_dir, "tex", [])

        monkeypatch.setattr(get_keywords, "get_keywords_from_gemini", lambda title, platform="net": ["kw"])

        state_path = tmp_path / "state.json"
        state = migrate.migrate_families(["tex"], [str(kb_site), str(docs_site)], str(output_dir), state_path=state_path)

        assert state["families"]["tex"]["status"] == "done"
        assert state["migration_complete"] is True
