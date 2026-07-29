"""SEO-SCHEMA-A-FIX-GENERATION-LOGIC: stable dedup-identity regression tests.

Reproduces Finding #32's orphaned-entry class of bug: get_keywords.py used
to match existing entries by exact `pageTitle` string only. When a page's
head_title changed (a rename, a copy-edit pass, a title-consistency
backfill -- anything this same mission's SEO-TITLE-* lane will eventually
do), the old title stayed in the JSON forever with nothing recognizing it as
the same page, while a new entry got created for the new title. Repeated
over enough renames, entries only ever accumulated -- this is the concrete
mechanism behind imaging.json's 249 orphaned entries.

The fix adds a `sourcePath` field (the page's repo-relative file path,
stable across title renames) as the primary match key, falling back to
pageTitle-only matching for legacy entries that predate the field.
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


def _write(path: Path, entries: list[dict]) -> None:
    path.write_text(json.dumps(entries, ensure_ascii=False), encoding="utf-8")


def test_find_entry_matches_by_source_path_even_if_title_changed(tmp_path):
    data = [{"pageTitle": "Old Title", "sourcePath": "content/kb.aspose.org/pdf/old-page.md", "keywords": ["a"]}]
    found = get_keywords._find_entry(data, "content/kb.aspose.org/pdf/old-page.md", "New Title")
    assert found is not None
    assert found["pageTitle"] == "Old Title"  # caller (append_keywords_to_existing) updates it


def test_find_entry_does_not_match_different_source_path_same_title(tmp_path):
    """Two distinct pages that happen to share a title must never merge."""
    data = [{"pageTitle": "Getting Started", "sourcePath": "content/kb.aspose.org/pdf/a.md", "keywords": ["a"]}]
    found = get_keywords._find_entry(data, "content/kb.aspose.org/pdf/b.md", "Getting Started")
    assert found is None


def test_find_entry_falls_back_to_title_for_legacy_entries_without_source_path():
    data = [{"pageTitle": "Legacy Title", "keywords": ["a"]}]
    found = get_keywords._find_entry(data, "content/kb.aspose.org/pdf/legacy.md", "Legacy Title")
    assert found is not None
    assert found["pageTitle"] == "Legacy Title"


def test_find_entry_legacy_fallback_never_matches_a_sourcepath_tagged_entry_by_title():
    """A newer, sourcePath-tagged entry must not be silently matched by an
    unrelated page's title-only lookup -- that would defeat the fix."""
    data = [{"pageTitle": "Shared Title", "sourcePath": "content/kb.aspose.org/pdf/real.md", "keywords": ["a"]}]
    found = get_keywords._find_entry(data, "content/kb.aspose.org/pdf/other.md", "Shared Title")
    assert found is None


def test_append_keywords_updates_title_in_place_on_rename(tmp_path):
    family_file = tmp_path / "pdf.json"
    _write(family_file, [
        {"pageTitle": "Old Title", "sourcePath": "content/kb.aspose.org/pdf/page.md", "keywords": ["old-kw"]}
    ])

    get_keywords.append_keywords_to_existing(
        "pdf", "content/kb.aspose.org/pdf/page.md", "New Title", ["new-kw"], str(tmp_path)
    )

    data = json.loads(family_file.read_text(encoding="utf-8"))
    assert len(data) == 1  # no orphaned duplicate created
    assert data[0]["pageTitle"] == "New Title"
    assert set(data[0]["keywords"]) == {"old-kw", "new-kw"}
    assert data[0]["sourcePath"] == "content/kb.aspose.org/pdf/page.md"


def test_find_existing_entry_returns_none_for_new_page(tmp_path):
    family_file = tmp_path / "pdf.json"
    _write(family_file, [{"pageTitle": "Other Page", "sourcePath": "content/kb.aspose.org/pdf/other.md", "keywords": ["x"]}])

    found = get_keywords.find_existing_entry("pdf", "content/kb.aspose.org/pdf/new.md", "New Page", str(tmp_path))
    assert found is None


def test_find_existing_entry_missing_file_returns_none(tmp_path):
    found = get_keywords.find_existing_entry("nope", "content/x/y.md", "Title", str(tmp_path))
    assert found is None


def test_get_keywords_from_gemini_uses_platform_label_in_prompt(monkeypatch):
    """Finding #33: the Gemini prompt used to hardcode '.NET platform'
    regardless of the actual platform being processed."""
    captured = {}

    class _FakeResponse:
        text = "keyword one\nkeyword two"

    class _FakeModel:
        def __init__(self, *a, **kw):
            pass

        def generate_content(self, prompt):
            captured["prompt"] = prompt
            return _FakeResponse()

    import types
    fake_genai = types.SimpleNamespace(GenerativeModel=_FakeModel)
    monkeypatch.setitem(sys.modules, "google", types.SimpleNamespace(generativeai=fake_genai))
    monkeypatch.setitem(sys.modules, "google.generativeai", fake_genai)

    keywords = get_keywords.get_keywords_from_gemini("Some Page", platform="java")
    assert keywords == ["keyword one", "keyword two"]
    assert "Java platform" in captured["prompt"]
    assert ".NET" not in captured["prompt"]


def test_get_keywords_from_gemini_defaults_to_net_platform(monkeypatch):
    captured = {}

    class _FakeResponse:
        text = "kw"

    class _FakeModel:
        def __init__(self, *a, **kw):
            pass

        def generate_content(self, prompt):
            captured["prompt"] = prompt
            return _FakeResponse()

    import types
    fake_genai = types.SimpleNamespace(GenerativeModel=_FakeModel)
    monkeypatch.setitem(sys.modules, "google", types.SimpleNamespace(generativeai=fake_genai))
    monkeypatch.setitem(sys.modules, "google.generativeai", fake_genai)

    get_keywords.get_keywords_from_gemini("Some Page")
    assert ".NET platform" in captured["prompt"]
