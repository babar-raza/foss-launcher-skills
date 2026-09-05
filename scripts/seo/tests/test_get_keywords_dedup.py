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


@pytest.fixture(autouse=True)
def _allow_autonomy_gate(monkeypatch):
    """Default: every family is AUTONOMOUSLY_ELIGIBLE for schema_a_refresh,
    so these tests exercise dedup/circuit-breaker behavior rather than
    Contract I's own gate (covered by scripts/seo/tests/test_autonomy_state.py)."""
    monkeypatch.setattr(get_keywords.autonomy_state, "is_autonomously_eligible", lambda *a, **k: True)


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


def test_replace_keywords_for_entry_overwrites_not_unions(tmp_path):
    """Finding #52: replace_keywords_for_entry() exists specifically because
    append_keywords_to_existing()'s union semantics are wrong for a forced
    correction of a known-bad keyword set (e.g. the platform-mislabeling
    migration) -- the old keywords must not survive."""
    family_file = tmp_path / "pdf.json"
    _write(family_file, [
        {"pageTitle": "Same Title", "sourcePath": "content/kb.aspose.org/pdf/page.md", "keywords": ["wrong-platform-kw"]}
    ])

    get_keywords.replace_keywords_for_entry(
        "pdf", "content/kb.aspose.org/pdf/page.md", "Same Title", ["correct-kw"], str(tmp_path)
    )

    data = json.loads(family_file.read_text(encoding="utf-8"))
    assert len(data) == 1
    assert data[0]["keywords"] == ["correct-kw"]
    assert "wrong-platform-kw" not in data[0]["keywords"]
    assert data[0]["sourcePath"] == "content/kb.aspose.org/pdf/page.md"


def test_replace_keywords_for_entry_missing_file_is_a_noop(tmp_path):
    get_keywords.replace_keywords_for_entry("nope", "content/x/y.md", "Title", ["kw"], str(tmp_path))
    assert not (tmp_path / "nope.json").exists()


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
    monkeypatch.setattr(get_keywords.time, "sleep", lambda *a, **kw: None)

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
    monkeypatch.setattr(get_keywords.time, "sleep", lambda *a, **kw: None)

    get_keywords.get_keywords_from_gemini("Some Page")
    assert ".NET platform" in captured["prompt"]


def test_get_keywords_from_gemini_returns_none_after_exhausting_429_retries(monkeypatch):
    """Bounded retry (Gemini API limitations follow-up): a persistent 429
    must give up after _MAX_429_RETRIES, not retry forever."""
    call_count = {"n": 0}

    class _FakeModel:
        def __init__(self, *a, **kw):
            pass

        def generate_content(self, prompt):
            call_count["n"] += 1
            raise RuntimeError("429 Too Many Requests")

    import types
    fake_genai = types.SimpleNamespace(GenerativeModel=_FakeModel)
    monkeypatch.setitem(sys.modules, "google", types.SimpleNamespace(generativeai=fake_genai))
    monkeypatch.setitem(sys.modules, "google.generativeai", fake_genai)
    sleeps = []
    monkeypatch.setattr(get_keywords.time, "sleep", lambda s: sleeps.append(s))

    result = get_keywords.get_keywords_from_gemini("Some Page")
    assert result is None
    assert call_count["n"] == get_keywords._MAX_429_RETRIES
    # backoff grows with attempt number, never sleeps for the (would-be) pacing delay
    assert sleeps == [get_keywords._BACKOFF_BASE_SECONDS * a for a in range(1, get_keywords._MAX_429_RETRIES)]


def test_get_keywords_from_gemini_returns_none_on_non_429_error(monkeypatch):
    """A non-rate-limit error (e.g. a retired/renamed model returning 404)
    must return None -- distinct from [] ("Gemini suggested nothing") --
    so callers can count it as a hard failure."""
    class _FakeModel:
        def __init__(self, *a, **kw):
            pass

        def generate_content(self, prompt):
            raise RuntimeError("404 model not found")

    import types
    fake_genai = types.SimpleNamespace(GenerativeModel=_FakeModel)
    monkeypatch.setitem(sys.modules, "google", types.SimpleNamespace(generativeai=fake_genai))
    monkeypatch.setitem(sys.modules, "google.generativeai", fake_genai)
    monkeypatch.setattr(get_keywords.time, "sleep", lambda *a, **kw: None)

    result = get_keywords.get_keywords_from_gemini("Some Page")
    assert result is None


def test_process_markdown_files_raises_systemexit_when_every_call_fails(tmp_path, monkeypatch):
    """Gemini API limitations follow-up: a 100% failure rate (retired model,
    revoked key, exhausted quota) must fail loudly, not silently report as
    a healthy '0 changes' run indistinguishable from real idempotency."""
    monkeypatch.setattr(get_keywords, "_REPO_ROOT", tmp_path)
    family_dir = tmp_path / "cad"
    family_dir.mkdir()
    (family_dir / "_index.md").write_text(
        "---\ntitle: Aspose.CAD FOSS\n---\nBody\n", encoding="utf-8"
    )
    output_dir = tmp_path / "keywords"
    output_dir.mkdir()

    monkeypatch.setattr(get_keywords, "get_keywords_from_gemini", lambda title, platform="net": None)

    with pytest.raises(SystemExit):
        get_keywords.process_markdown_files_by_families(["cad"], str(tmp_path), str(output_dir))


def test_process_markdown_files_does_not_raise_when_some_calls_succeed(tmp_path, monkeypatch):
    """Partial failure (normal transient throttling) must not be treated as
    the systemic case -- only a 100% failure rate is loud."""
    monkeypatch.setattr(get_keywords, "_REPO_ROOT", tmp_path)
    family_dir = tmp_path / "cad"
    family_dir.mkdir()
    (family_dir / "_index.md").write_text(
        "---\ntitle: Aspose.CAD FOSS\n---\nBody\n", encoding="utf-8"
    )
    output_dir = tmp_path / "keywords"
    output_dir.mkdir()

    monkeypatch.setattr(get_keywords, "get_keywords_from_gemini", lambda title, platform="net": ["a keyword"])

    result = get_keywords.process_markdown_files_by_families(["cad"], str(tmp_path), str(output_dir))
    assert result["cad"][0]["keywords"] == ["a keyword"]


def test_process_markdown_files_circuit_breaker_stops_after_consecutive_failures(tmp_path, monkeypatch):
    """Found live 2026-07-31/08-01: without a whole-run circuit breaker, a
    sustained quota exhaustion meant ~8.5 hours grinding through 48
    consecutive pages one at a time, each burning its full per-page retry
    budget, with zero successes the entire time. 3 consecutive failures
    must stop the run immediately rather than continuing to the 4th, 5th...
    file in the list."""
    monkeypatch.setattr(get_keywords, "_REPO_ROOT", tmp_path)
    family_dir = tmp_path / "cad"
    family_dir.mkdir()
    for i in range(6):
        (family_dir / f"page{i}.md").write_text(
            f"---\ntitle: Page {i}\n---\nBody\n", encoding="utf-8"
        )
    output_dir = tmp_path / "keywords"
    output_dir.mkdir()

    call_count = {"n": 0}

    def _always_fail(title, platform="net"):
        call_count["n"] += 1
        return None

    monkeypatch.setattr(get_keywords, "get_keywords_from_gemini", _always_fail)

    with pytest.raises(SystemExit):
        get_keywords.process_markdown_files_by_families(["cad"], str(tmp_path), str(output_dir))

    assert call_count["n"] == get_keywords._CIRCUIT_BREAKER_CONSECUTIVE_FAILURES, (
        "circuit breaker must stop the run at exactly the threshold, not process "
        "all 6 files in the family"
    )


def test_process_markdown_files_circuit_breaker_resets_on_success(tmp_path, monkeypatch):
    """Alternating success/failure (normal transient throttling) must never
    trip the breaker, however many total failures accumulate, as long as
    they're not consecutive."""
    monkeypatch.setattr(get_keywords, "_REPO_ROOT", tmp_path)
    family_dir = tmp_path / "cad"
    family_dir.mkdir()
    for i in range(6):
        (family_dir / f"page{i}.md").write_text(
            f"---\ntitle: Page {i}\n---\nBody\n", encoding="utf-8"
        )
    output_dir = tmp_path / "keywords"
    output_dir.mkdir()

    call_count = {"n": 0}

    def _alternate(title, platform="net"):
        call_count["n"] += 1
        return None if call_count["n"] % 2 == 0 else ["a keyword"]

    monkeypatch.setattr(get_keywords, "get_keywords_from_gemini", _alternate)

    result = get_keywords.process_markdown_files_by_families(["cad"], str(tmp_path), str(output_dir))
    assert call_count["n"] == 6, "all 6 files must be processed -- no consecutive-failure run ever occurred"
    assert len(result["cad"]) == 3
