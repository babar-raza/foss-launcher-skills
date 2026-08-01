"""SEO-SCHEMA-A-WORKFLOW-UPDATE: per-file platform extraction regression tests (Finding #50).

get_keywords.py used to trust a single CLI-wide --platform flag for every
file regardless of the file's real platform -- confirmed directly in
already-committed data: a TypeScript page's generated keywords included
".NET core tutorial"-style phrases. The fix derives the real platform from
each file's own path ({family}/{platform}/...) instead, falling back to a
platform-neutral prompt for family-root pages that have no single platform.
"""
from __future__ import annotations

import datetime
import sys
import types
from pathlib import Path

import pytest

_SCRIPTS = Path(__file__).resolve().parents[2]
_PIPELINE = _SCRIPTS / "pipeline"
if str(_SCRIPTS) not in sys.path:
    sys.path.insert(0, str(_SCRIPTS))
if str(_PIPELINE) not in sys.path:
    sys.path.insert(0, str(_PIPELINE))

import seo.get_keywords as get_keywords  # noqa: E402


def _fake_genai(monkeypatch, captured):
    class _FakeResponse:
        text = "kw one\nkw two"

    class _FakeModel:
        def __init__(self, *a, **kw):
            pass

        def generate_content(self, prompt):
            captured["prompt"] = prompt
            return _FakeResponse()

    fake_genai = types.SimpleNamespace(GenerativeModel=_FakeModel)
    monkeypatch.setitem(sys.modules, "google", types.SimpleNamespace(generativeai=fake_genai))
    monkeypatch.setitem(sys.modules, "google.generativeai", fake_genai)
    monkeypatch.setattr(get_keywords.time, "sleep", lambda *a, **kw: None)


class TestExtractPlatformFromPath:
    def test_nested_platform_directory_is_extracted(self, tmp_path):
        family_dir = tmp_path / "3d"
        file_path = family_dir / "typescript" / "getting-started" / "quickstart.md"
        assert get_keywords._extract_platform_from_path(str(file_path), str(family_dir)) == "typescript"

    def test_family_root_index_returns_none(self, tmp_path):
        family_dir = tmp_path / "3d"
        file_path = family_dir / "_index.md"
        assert get_keywords._extract_platform_from_path(str(file_path), str(family_dir)) is None

    def test_platform_index_page_is_extracted(self, tmp_path):
        family_dir = tmp_path / "pdf"
        file_path = family_dir / "java" / "_index.md"
        assert get_keywords._extract_platform_from_path(str(file_path), str(family_dir)) == "java"


class TestGetKeywordsFromGeminiPlatformFraming:
    def test_platform_none_produces_neutral_prompt(self, monkeypatch):
        captured = {}
        _fake_genai(monkeypatch, captured)
        get_keywords.get_keywords_from_gemini("Some Page", platform=None)
        assert ".NET" not in captured["prompt"]
        assert "this product" in captured["prompt"]

    @pytest.mark.parametrize("platform,expected_label", [
        ("go", "Go"),
        ("rust", "Rust"),
        ("typescript", "TypeScript"),
    ])
    def test_new_platform_labels(self, monkeypatch, platform, expected_label):
        captured = {}
        _fake_genai(monkeypatch, captured)
        get_keywords.get_keywords_from_gemini("Some Page", platform=platform)
        assert f"the {expected_label} platform" in captured["prompt"]
        assert ".NET" not in captured["prompt"]


class TestProcessMarkdownFilesPlatformDetection:
    def test_nested_file_uses_detected_platform_not_net_default(self, tmp_path, monkeypatch):
        monkeypatch.setattr(get_keywords, "_REPO_ROOT", tmp_path)
        family_dir = tmp_path / "3d"
        (family_dir / "typescript" / "getting-started").mkdir(parents=True)
        (family_dir / "typescript" / "getting-started" / "quickstart.md").write_text(
            "---\ntitle: Aspose.3D FOSS for TypeScript Quickstart\n---\nBody\n", encoding="utf-8"
        )
        output_dir = tmp_path / "keywords"
        output_dir.mkdir()

        captured_platforms = []

        def _fake_call(title, platform="net"):
            captured_platforms.append(platform)
            return ["a keyword"]

        monkeypatch.setattr(get_keywords, "get_keywords_from_gemini", _fake_call)

        get_keywords.process_markdown_files_by_families(["3d"], str(tmp_path), str(output_dir))
        assert captured_platforms == ["typescript"]

    def test_family_root_file_gets_platform_none(self, tmp_path, monkeypatch):
        monkeypatch.setattr(get_keywords, "_REPO_ROOT", tmp_path)
        family_dir = tmp_path / "3d"
        family_dir.mkdir()
        (family_dir / "_index.md").write_text(
            "---\ntitle: Aspose.3D FOSS\n---\nBody\n", encoding="utf-8"
        )
        output_dir = tmp_path / "keywords"
        output_dir.mkdir()

        captured_platforms = []

        def _fake_call(title, platform="net"):
            captured_platforms.append(platform)
            return ["a keyword"]

        monkeypatch.setattr(get_keywords, "get_keywords_from_gemini", _fake_call)

        get_keywords.process_markdown_files_by_families(["3d"], str(tmp_path), str(output_dir))
        assert captured_platforms == [None]

    def test_platform_override_forces_fixed_platform(self, tmp_path, monkeypatch):
        monkeypatch.setattr(get_keywords, "_REPO_ROOT", tmp_path)
        family_dir = tmp_path / "3d"
        (family_dir / "typescript").mkdir(parents=True)
        (family_dir / "typescript" / "quickstart.md").write_text(
            "---\ntitle: Aspose.3D FOSS for TypeScript Quickstart\n---\nBody\n", encoding="utf-8"
        )
        output_dir = tmp_path / "keywords"
        output_dir.mkdir()

        captured_platforms = []

        def _fake_call(title, platform="net"):
            captured_platforms.append(platform)
            return ["a keyword"]

        monkeypatch.setattr(get_keywords, "get_keywords_from_gemini", _fake_call)

        get_keywords.process_markdown_files_by_families(
            ["3d"], str(tmp_path), str(output_dir), platform_override="java"
        )
        assert captured_platforms == ["java"]


class TestRotateFamiliesByIsoWeek:
    def test_rotation_matches_the_formula_for_a_given_week(self):
        families = ["a", "b", "c", "d"]
        a_date = datetime.date(2026, 1, 5)
        result = get_keywords.rotate_families_by_iso_week(families, today=a_date)
        iso_week = a_date.isocalendar()[1]
        expected_start = iso_week % len(families)
        assert result[0] == families[expected_start]
        assert set(result) == set(families)
        assert len(result) == len(families)

    def test_rotation_differs_across_weeks_apart_by_one(self):
        families = ["a", "b", "c"]
        week_n = get_keywords.rotate_families_by_iso_week(families, today=datetime.date(2026, 1, 5))
        week_n_plus_1 = get_keywords.rotate_families_by_iso_week(families, today=datetime.date(2026, 1, 12))
        assert week_n != week_n_plus_1

    def test_empty_families_returns_empty(self):
        assert get_keywords.rotate_families_by_iso_week([]) == []
