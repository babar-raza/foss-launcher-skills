"""SEO-SCHEMA-A-FIX-GENERATION-LOGIC: review_keywords.py platform-bias +
sourcePath-preservation regression tests (companion to test_get_keywords_dedup.py
-- review_keywords.py had the identical hardcoded '.NET platform' bug,
independently, in its own Gemini reevaluation prompt).
"""
from __future__ import annotations

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

import seo.review_keywords as review_keywords  # noqa: E402


def test_merge_keywords_by_title_unions_keyword_sets():
    data = [
        {"pageTitle": "How To X", "keywords": ["a", "b"]},
        {"pageTitle": "How To X", "keywords": ["b", "c"]},
    ]
    merged = review_keywords.merge_keywords_by_title(data)
    assert len(merged) == 1
    assert set(merged[0]["keywords"]) == {"a", "b", "c"}


def test_merge_keywords_by_title_carries_sourcepath_forward():
    data = [
        {"pageTitle": "How To X", "sourcePath": "content/kb.aspose.org/pdf/x.md", "keywords": ["a"]},
        {"pageTitle": "How To X", "keywords": ["b"]},
    ]
    merged = review_keywords.merge_keywords_by_title(data)
    assert merged[0]["sourcePath"] == "content/kb.aspose.org/pdf/x.md"


def test_merge_keywords_by_title_omits_sourcepath_when_none_present():
    data = [{"pageTitle": "How To X", "keywords": ["a"]}]
    merged = review_keywords.merge_keywords_by_title(data)
    assert "sourcePath" not in merged[0]


def test_merge_keywords_by_title_skips_entries_missing_title():
    data = [{"keywords": ["a"]}, {"pageTitle": "Real", "keywords": ["b"]}]
    merged = review_keywords.merge_keywords_by_title(data)
    assert len(merged) == 1
    assert merged[0]["pageTitle"] == "Real"


def test_reevaluate_keywords_uses_platform_label(monkeypatch):
    captured = {}

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
    monkeypatch.setattr(review_keywords.time, "sleep", lambda *a, **kw: None)

    result = review_keywords.reevaluate_keywords("Title", ["a", "b"], platform="python")
    assert result == ["kw one", "kw two"]
    assert "Python platform" in captured["prompt"]
    assert ".NET" not in captured["prompt"]


def test_reevaluate_keywords_defaults_to_net_platform(monkeypatch):
    captured = {}

    class _FakeResponse:
        text = "kw"

    class _FakeModel:
        def __init__(self, *a, **kw):
            pass

        def generate_content(self, prompt):
            captured["prompt"] = prompt
            return _FakeResponse()

    fake_genai = types.SimpleNamespace(GenerativeModel=_FakeModel)
    monkeypatch.setitem(sys.modules, "google", types.SimpleNamespace(generativeai=fake_genai))
    monkeypatch.setitem(sys.modules, "google.generativeai", fake_genai)
    monkeypatch.setattr(review_keywords.time, "sleep", lambda *a, **kw: None)

    review_keywords.reevaluate_keywords("Title", ["a"])
    assert ".NET platform" in captured["prompt"]


def test_reevaluate_keywords_returns_none_after_exhausting_429_retries(monkeypatch):
    call_count = {"n": 0}

    class _FakeModel:
        def __init__(self, *a, **kw):
            pass

        def generate_content(self, prompt):
            call_count["n"] += 1
            raise RuntimeError("429 Too Many Requests")

    fake_genai = types.SimpleNamespace(GenerativeModel=_FakeModel)
    monkeypatch.setitem(sys.modules, "google", types.SimpleNamespace(generativeai=fake_genai))
    monkeypatch.setitem(sys.modules, "google.generativeai", fake_genai)
    monkeypatch.setattr(review_keywords.time, "sleep", lambda *a, **kw: None)

    result = review_keywords.reevaluate_keywords("Title", ["a"])
    assert result is None
    assert call_count["n"] == review_keywords._MAX_429_RETRIES


def test_process_json_files_raises_systemexit_when_every_call_fails(tmp_path, monkeypatch):
    family_file = tmp_path / "cad.json"
    family_file.write_text(
        '[{"pageTitle": "Aspose.CAD FOSS", "keywords": ["a keyword"]}]',
        encoding="utf-8",
    )

    monkeypatch.setattr(review_keywords, "reevaluate_keywords", lambda title, kws, platform="net": None)

    with pytest.raises(SystemExit):
        review_keywords.process_json_files_by_family(["cad"], str(tmp_path))
