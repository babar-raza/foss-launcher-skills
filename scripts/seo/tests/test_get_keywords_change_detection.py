"""SEO-SCHEMA-A-WORKFLOW-UPDATE: change-detection (skip-if-unchanged) and
call-budget regression tests (Finding #51).

get_keywords.py used to call Gemini for every file in scope on every run,
regardless of whether anything changed since the last run -- a naive weekly
full-corpus cron would immediately exceed the real, empirically-tight quota
ceiling the bootstrap regeneration discovered (SEO-SCHEMA-A-BOOTSTRAP-
REGENERATION, ~350-400 calls before sustained exhaustion). The fix skips the
call entirely when an existing entry's title is unchanged, and adds a
proactive --max-calls budget independent of the reactive circuit breaker.
"""
from __future__ import annotations

import json
import sys
from pathlib import Path

import pytest

_SCRIPTS = Path(__file__).resolve().parents[2]
_PIPELINE = _SCRIPTS / "pipeline"
if str(_SCRIPTS) not in sys.path:
    sys.path.insert(0, str(_SCRIPTS))
if str(_PIPELINE) not in sys.path:
    sys.path.insert(0, str(_PIPELINE))

import seo.get_keywords as get_keywords  # noqa: E402


@pytest.fixture(autouse=True)
def _allow_autonomy_gate(monkeypatch):
    """Default: every family is AUTONOMOUSLY_ELIGIBLE for schema_a_refresh,
    so these tests exercise change-detection/budget behavior rather than
    Contract I's own gate (covered by scripts/seo/tests/test_autonomy_state.py)."""
    monkeypatch.setattr(get_keywords.autonomy_state, "is_autonomously_eligible", lambda *a, **k: True)


def _write_family_json(output_dir, family, entries):
    (output_dir / f"{family}.json").write_text(json.dumps(entries), encoding="utf-8")


def _source_path(tmp_path, family_dir, filename):
    return Path(family_dir / filename).resolve().relative_to(tmp_path).as_posix()


class TestAutonomyStateGate:
    """SEO-AUTONOMY-STATE-MACHINE (Contract I) read-gate: a family not
    AUTONOMOUSLY_ELIGIBLE for schema_a_refresh is skipped entirely, never
    silently processed. State-machine correctness itself lives in
    test_autonomy_state.py; this only proves get_keywords.py's per-family
    loop actually calls the gate."""

    def test_family_skipped_when_not_eligible(self, tmp_path, monkeypatch):
        monkeypatch.setattr(get_keywords, "_REPO_ROOT", tmp_path)
        monkeypatch.setattr(get_keywords.autonomy_state, "is_autonomously_eligible", lambda *a, **k: False)
        family_dir = tmp_path / "tex"
        family_dir.mkdir()
        (family_dir / "page.md").write_text("---\ntitle: Some Title\n---\nBody\n", encoding="utf-8")
        output_dir = tmp_path / "keywords"
        output_dir.mkdir()

        call_count = {"n": 0}

        def _fake_call(title, platform="net"):
            call_count["n"] += 1
            return ["new"]

        monkeypatch.setattr(get_keywords, "get_keywords_from_gemini", _fake_call)

        family_data = get_keywords.process_markdown_files_by_families(
            ["tex"], str(tmp_path), str(output_dir)
        )

        assert call_count["n"] == 0, "an ineligible family must never reach the Gemini call"
        assert "tex" not in family_data, "a skipped family contributes no entries at all"

    def test_family_processed_when_eligible(self, tmp_path, monkeypatch):
        monkeypatch.setattr(get_keywords, "_REPO_ROOT", tmp_path)
        monkeypatch.setattr(get_keywords.autonomy_state, "is_autonomously_eligible", lambda *a, **k: True)
        family_dir = tmp_path / "tex"
        family_dir.mkdir()
        (family_dir / "page.md").write_text("---\ntitle: Some Title\n---\nBody\n", encoding="utf-8")
        output_dir = tmp_path / "keywords"
        output_dir.mkdir()
        monkeypatch.setattr(get_keywords, "get_keywords_from_gemini", lambda title, platform="net": ["new"])

        family_data = get_keywords.process_markdown_files_by_families(
            ["tex"], str(tmp_path), str(output_dir)
        )

        assert "tex" in family_data
        assert len(family_data["tex"]) == 1


class TestSkipIfUnchanged:
    def test_unchanged_title_skips_the_call(self, tmp_path, monkeypatch):
        monkeypatch.setattr(get_keywords, "_REPO_ROOT", tmp_path)
        family_dir = tmp_path / "tex"
        family_dir.mkdir()
        (family_dir / "page.md").write_text("---\ntitle: Same Title\n---\nBody\n", encoding="utf-8")
        output_dir = tmp_path / "keywords"
        output_dir.mkdir()
        _write_family_json(output_dir, "tex", [
            {"pageTitle": "Same Title", "sourcePath": _source_path(tmp_path, family_dir, "page.md"), "keywords": ["old"]}
        ])

        call_count = {"n": 0}

        def _fake_call(title, platform="net"):
            call_count["n"] += 1
            return ["new"]

        monkeypatch.setattr(get_keywords, "get_keywords_from_gemini", _fake_call)

        get_keywords.process_markdown_files_by_families(["tex"], str(tmp_path), str(output_dir))
        assert call_count["n"] == 0

    def test_changed_title_still_calls_and_appends(self, tmp_path, monkeypatch):
        monkeypatch.setattr(get_keywords, "_REPO_ROOT", tmp_path)
        family_dir = tmp_path / "tex"
        family_dir.mkdir()
        (family_dir / "page.md").write_text("---\ntitle: New Title\n---\nBody\n", encoding="utf-8")
        output_dir = tmp_path / "keywords"
        output_dir.mkdir()
        _write_family_json(output_dir, "tex", [
            {"pageTitle": "Old Title", "sourcePath": _source_path(tmp_path, family_dir, "page.md"), "keywords": ["old"]}
        ])

        call_count = {"n": 0}

        def _fake_call(title, platform="net"):
            call_count["n"] += 1
            return ["new"]

        monkeypatch.setattr(get_keywords, "get_keywords_from_gemini", _fake_call)

        get_keywords.process_markdown_files_by_families(["tex"], str(tmp_path), str(output_dir))
        assert call_count["n"] == 1
        data = json.loads((output_dir / "tex.json").read_text(encoding="utf-8"))
        assert data[0]["pageTitle"] == "New Title"
        assert set(data[0]["keywords"]) == {"old", "new"}

    def test_new_page_always_calls(self, tmp_path, monkeypatch):
        monkeypatch.setattr(get_keywords, "_REPO_ROOT", tmp_path)
        family_dir = tmp_path / "tex"
        family_dir.mkdir()
        (family_dir / "page.md").write_text("---\ntitle: Brand New\n---\nBody\n", encoding="utf-8")
        output_dir = tmp_path / "keywords"
        output_dir.mkdir()

        call_count = {"n": 0}

        def _fake_call(title, platform="net"):
            call_count["n"] += 1
            return ["kw"]

        monkeypatch.setattr(get_keywords, "get_keywords_from_gemini", _fake_call)

        get_keywords.process_markdown_files_by_families(["tex"], str(tmp_path), str(output_dir))
        assert call_count["n"] == 1

    def test_force_bypasses_skip_even_when_unchanged(self, tmp_path, monkeypatch):
        monkeypatch.setattr(get_keywords, "_REPO_ROOT", tmp_path)
        family_dir = tmp_path / "tex"
        family_dir.mkdir()
        (family_dir / "page.md").write_text("---\ntitle: Same Title\n---\nBody\n", encoding="utf-8")
        output_dir = tmp_path / "keywords"
        output_dir.mkdir()
        _write_family_json(output_dir, "tex", [
            {"pageTitle": "Same Title", "sourcePath": _source_path(tmp_path, family_dir, "page.md"), "keywords": ["old"]}
        ])

        call_count = {"n": 0}

        def _fake_call(title, platform="net"):
            call_count["n"] += 1
            return ["new"]

        monkeypatch.setattr(get_keywords, "get_keywords_from_gemini", _fake_call)

        get_keywords.process_markdown_files_by_families(["tex"], str(tmp_path), str(output_dir), force=True)
        assert call_count["n"] == 1

    def test_force_with_unchanged_title_replaces_not_unions(self, tmp_path, monkeypatch):
        """Finding #52: --force with an unchanged title is a genuine forced
        correction (e.g. the platform-mislabeling migration) -- the old,
        known-wrong keywords must be GONE afterward, not unioned with the
        new ones. Before the fix, this entry would have ended up with
        {"old", "new"} -- a permanently contaminated mix."""
        monkeypatch.setattr(get_keywords, "_REPO_ROOT", tmp_path)
        family_dir = tmp_path / "tex"
        family_dir.mkdir()
        (family_dir / "page.md").write_text("---\ntitle: Same Title\n---\nBody\n", encoding="utf-8")
        output_dir = tmp_path / "keywords"
        output_dir.mkdir()
        _write_family_json(output_dir, "tex", [
            {"pageTitle": "Same Title", "sourcePath": _source_path(tmp_path, family_dir, "page.md"), "keywords": ["old"]}
        ])

        monkeypatch.setattr(get_keywords, "get_keywords_from_gemini", lambda title, platform="net": ["new"])

        get_keywords.process_markdown_files_by_families(["tex"], str(tmp_path), str(output_dir), force=True)

        data = json.loads((output_dir / "tex.json").read_text(encoding="utf-8"))
        assert set(data[0]["keywords"]) == {"new"}, "old, known-wrong keywords must not survive a forced correction"

    def test_force_with_genuine_title_change_still_unions(self, tmp_path, monkeypatch):
        """Regression pin: force=True must not change the REAL-rename case --
        a title that actually changed still unions, exactly as before
        Finding #52's fix (accumulating keyword variety is correct there)."""
        monkeypatch.setattr(get_keywords, "_REPO_ROOT", tmp_path)
        family_dir = tmp_path / "tex"
        family_dir.mkdir()
        (family_dir / "page.md").write_text("---\ntitle: New Title\n---\nBody\n", encoding="utf-8")
        output_dir = tmp_path / "keywords"
        output_dir.mkdir()
        _write_family_json(output_dir, "tex", [
            {"pageTitle": "Old Title", "sourcePath": _source_path(tmp_path, family_dir, "page.md"), "keywords": ["old"]}
        ])

        monkeypatch.setattr(get_keywords, "get_keywords_from_gemini", lambda title, platform="net": ["new"])

        get_keywords.process_markdown_files_by_families(["tex"], str(tmp_path), str(output_dir), force=True)

        data = json.loads((output_dir / "tex.json").read_text(encoding="utf-8"))
        assert data[0]["pageTitle"] == "New Title"
        assert set(data[0]["keywords"]) == {"old", "new"}


class TestMaxCallsBudget:
    def test_budget_stops_cleanly_without_systemexit(self, tmp_path, monkeypatch):
        monkeypatch.setattr(get_keywords, "_REPO_ROOT", tmp_path)
        family_dir = tmp_path / "tex"
        family_dir.mkdir()
        for i in range(10):
            (family_dir / f"page{i}.md").write_text(f"---\ntitle: Page {i}\n---\nBody\n", encoding="utf-8")
        output_dir = tmp_path / "keywords"
        output_dir.mkdir()

        call_count = {"n": 0}

        def _fake_call(title, platform="net"):
            call_count["n"] += 1
            return ["kw"]

        monkeypatch.setattr(get_keywords, "get_keywords_from_gemini", _fake_call)

        # Must return normally (not raise SystemExit) -- pytest.raises is
        # deliberately NOT used here; an unexpected SystemExit fails the test.
        result = get_keywords.process_markdown_files_by_families(
            ["tex"], str(tmp_path), str(output_dir), max_calls=5
        )
        assert call_count["n"] == 5
        assert len(result["tex"]) == 5

    def test_budget_reached_message_is_printed_not_swallowed(self, tmp_path, monkeypatch, capsys):
        monkeypatch.setattr(get_keywords, "_REPO_ROOT", tmp_path)
        family_dir = tmp_path / "tex"
        family_dir.mkdir()
        for i in range(3):
            (family_dir / f"page{i}.md").write_text(f"---\ntitle: Page {i}\n---\nBody\n", encoding="utf-8")
        output_dir = tmp_path / "keywords"
        output_dir.mkdir()

        monkeypatch.setattr(get_keywords, "get_keywords_from_gemini", lambda title, platform="net": ["kw"])

        get_keywords.process_markdown_files_by_families(["tex"], str(tmp_path), str(output_dir), max_calls=1)
        captured = capsys.readouterr()
        assert "budget" in captured.out.lower()

    def test_no_budget_processes_everything(self, tmp_path, monkeypatch):
        monkeypatch.setattr(get_keywords, "_REPO_ROOT", tmp_path)
        family_dir = tmp_path / "tex"
        family_dir.mkdir()
        (family_dir / "page.md").write_text("---\ntitle: Only Page\n---\nBody\n", encoding="utf-8")
        output_dir = tmp_path / "keywords"
        output_dir.mkdir()

        monkeypatch.setattr(get_keywords, "get_keywords_from_gemini", lambda title, platform="net": ["kw"])

        result = get_keywords.process_markdown_files_by_families(
            ["tex"], str(tmp_path), str(output_dir), max_calls=100
        )
        assert len(result["tex"]) == 1
