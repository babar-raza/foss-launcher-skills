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


# --- SEO-SCHEMA-A-DUAL-FIELD-GENERATION (Finding #57 Section J) ---


def test_keywords_with_variants_behaves_as_a_plain_list():
    kw = get_keywords.KeywordsWithVariants(["a", "b"], {"a": "A Title"})
    assert kw == ["a", "b"]
    assert list(kw) == ["a", "b"]
    assert set(kw) == {"a", "b"}
    assert kw.title_variants == {"a": "A Title"}


def test_parse_gemini_keyword_response_dual_field():
    text = "keyword one|Keyword One Title\nkeyword two|Keyword Two Title"
    phrases, variants = get_keywords._parse_gemini_keyword_response(text)
    assert phrases == ["keyword one", "keyword two"]
    assert variants == {"keyword one": "Keyword One Title", "keyword two": "Keyword Two Title"}


def test_parse_gemini_keyword_response_tolerates_missing_pipe():
    """A model that ignores the format on one line must not lose that
    phrase -- only the (optional) variant for that one line is absent."""
    text = "keyword one|Keyword One Title\nkeyword two\nkeyword three|Keyword Three Title"
    phrases, variants = get_keywords._parse_gemini_keyword_response(text)
    assert phrases == ["keyword one", "keyword two", "keyword three"]
    assert variants == {"keyword one": "Keyword One Title", "keyword three": "Keyword Three Title"}


def test_get_keywords_from_gemini_returns_keywords_with_variants(monkeypatch):
    class _FakeResponse:
        text = "quick start guide|Quick Start Guide\nsetup tutorial|Setup Tutorial"

    class _FakeModel:
        def __init__(self, *a, **kw):
            pass

        def generate_content(self, prompt):
            return _FakeResponse()

    import types
    fake_genai = types.SimpleNamespace(GenerativeModel=_FakeModel)
    monkeypatch.setitem(sys.modules, "google", types.SimpleNamespace(generativeai=fake_genai))
    monkeypatch.setitem(sys.modules, "google.generativeai", fake_genai)
    monkeypatch.setattr(get_keywords.time, "sleep", lambda *a, **kw: None)

    result = get_keywords.get_keywords_from_gemini("Some Page", platform="java")
    assert isinstance(result, get_keywords.KeywordsWithVariants)
    assert result == ["quick start guide", "setup tutorial"]
    assert result.title_variants == {
        "quick start guide": "Quick Start Guide",
        "setup tutorial": "Setup Tutorial",
    }


def test_append_keywords_to_existing_merges_title_ready_variants(tmp_path):
    family_file = tmp_path / "pdf.json"
    _write(family_file, [
        {
            "pageTitle": "Title",
            "sourcePath": "content/kb.aspose.org/pdf/page.md",
            "keywords": ["old-kw"],
            "title_ready_variants": {"old-kw": "Old Kw Title"},
            "schema_version": 2,
        }
    ])
    new_keywords = get_keywords.KeywordsWithVariants(["new-kw"], {"new-kw": "New Kw Title"})

    get_keywords.append_keywords_to_existing(
        "pdf", "content/kb.aspose.org/pdf/page.md", "Title", new_keywords, str(tmp_path)
    )

    data = json.loads(family_file.read_text(encoding="utf-8"))
    assert data[0]["title_ready_variants"] == {"old-kw": "Old Kw Title", "new-kw": "New Kw Title"}
    assert data[0]["schema_version"] == 2


def test_append_keywords_to_existing_with_plain_list_leaves_variants_untouched(tmp_path):
    """A legacy caller / test mock that returns a plain list (no
    .title_variants) must not disturb an entry's existing variants map."""
    family_file = tmp_path / "pdf.json"
    _write(family_file, [
        {
            "pageTitle": "Title",
            "sourcePath": "content/kb.aspose.org/pdf/page.md",
            "keywords": ["old-kw"],
            "title_ready_variants": {"old-kw": "Old Kw Title"},
            "schema_version": 2,
        }
    ])

    get_keywords.append_keywords_to_existing(
        "pdf", "content/kb.aspose.org/pdf/page.md", "Title", ["new-kw"], str(tmp_path)
    )

    data = json.loads(family_file.read_text(encoding="utf-8"))
    assert data[0]["title_ready_variants"] == {"old-kw": "Old Kw Title"}


def test_replace_keywords_for_entry_replaces_title_ready_variants(tmp_path):
    family_file = tmp_path / "pdf.json"
    _write(family_file, [
        {
            "pageTitle": "Title",
            "sourcePath": "content/kb.aspose.org/pdf/page.md",
            "keywords": ["wrong-kw"],
            "title_ready_variants": {"wrong-kw": "Wrong Title"},
            "schema_version": 2,
        }
    ])
    new_keywords = get_keywords.KeywordsWithVariants(["correct-kw"], {"correct-kw": "Correct Title"})

    get_keywords.replace_keywords_for_entry(
        "pdf", "content/kb.aspose.org/pdf/page.md", "Title", new_keywords, str(tmp_path)
    )

    data = json.loads(family_file.read_text(encoding="utf-8"))
    assert data[0]["title_ready_variants"] == {"correct-kw": "Correct Title"}
    assert "wrong-kw" not in data[0]["title_ready_variants"]


def test_replace_keywords_for_entry_drops_stale_variants_when_none_produced(tmp_path):
    """A forced replace with a plain list (no variants) must not leave a
    now-mismatched variants map (keyed to keywords that no longer exist on
    this entry) lying around."""
    family_file = tmp_path / "pdf.json"
    _write(family_file, [
        {
            "pageTitle": "Title",
            "sourcePath": "content/kb.aspose.org/pdf/page.md",
            "keywords": ["wrong-kw"],
            "title_ready_variants": {"wrong-kw": "Wrong Title"},
            "schema_version": 2,
        }
    ])

    get_keywords.replace_keywords_for_entry(
        "pdf", "content/kb.aspose.org/pdf/page.md", "Title", ["correct-kw"], str(tmp_path)
    )

    data = json.loads(family_file.read_text(encoding="utf-8"))
    assert "title_ready_variants" not in data[0]


def test_new_entry_gets_title_ready_variants_when_gemini_provides_them(tmp_path, monkeypatch):
    monkeypatch.setattr(get_keywords, "_REPO_ROOT", tmp_path)
    monkeypatch.setattr(get_keywords.autonomy_state, "is_autonomously_eligible", lambda *a, **k: True)
    family_dir = tmp_path / "tex"
    family_dir.mkdir()
    (family_dir / "page.md").write_text("---\ntitle: Brand New\n---\nBody\n", encoding="utf-8")
    output_dir = tmp_path / "keywords"
    output_dir.mkdir()

    fake_result = get_keywords.KeywordsWithVariants(["kw"], {"kw": "Kw Title"})
    monkeypatch.setattr(get_keywords, "get_keywords_from_gemini", lambda title, platform="net": fake_result)

    get_keywords.process_markdown_files_by_families(["tex"], str(tmp_path), str(output_dir))

    data = json.loads((output_dir / "tex.json").read_text(encoding="utf-8"))
    assert data[0]["title_ready_variants"] == {"kw": "Kw Title"}
    assert data[0]["schema_version"] == 2


def test_new_entry_with_plain_list_has_no_dual_field_keys(tmp_path, monkeypatch):
    """Every existing test mock (a plain list) must keep producing exactly
    the old 3-key entry shape -- no silent new keys appearing."""
    monkeypatch.setattr(get_keywords, "_REPO_ROOT", tmp_path)
    monkeypatch.setattr(get_keywords.autonomy_state, "is_autonomously_eligible", lambda *a, **k: True)
    family_dir = tmp_path / "tex"
    family_dir.mkdir()
    (family_dir / "page.md").write_text("---\ntitle: Brand New\n---\nBody\n", encoding="utf-8")
    output_dir = tmp_path / "keywords"
    output_dir.mkdir()

    monkeypatch.setattr(get_keywords, "get_keywords_from_gemini", lambda title, platform="net": ["kw"])

    get_keywords.process_markdown_files_by_families(["tex"], str(tmp_path), str(output_dir))

    data = json.loads((output_dir / "tex.json").read_text(encoding="utf-8"))
    assert set(data[0].keys()) == {"pageTitle", "sourcePath", "keywords"}


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


class TestPassesGroundingGate:
    """SEO-SCHEMA-A-BARCODE-CELLS-PLATFORM-LICENSE-REMEDIATION: the hard
    verify-and-retry gate generalized from the earlier remediation's rework
    fix (zero tolerance for any banned term, minimum required-term ratio)."""

    def test_empty_phrases_fail(self):
        assert get_keywords._passes_grounding_gate([], ["python"], [".net"], 0.7) is False

    def test_any_banned_term_anywhere_fails_even_if_required_terms_met(self):
        phrases = ["python excel reader", "python .net wrapper for excel"]
        assert get_keywords._passes_grounding_gate(phrases, ["python"], [".net"], 0.5) is False

    def test_required_ratio_met_passes(self):
        phrases = ["python excel reader", "python csv export", "generic excel tips"]
        # 2 of 3 mention "python" -> 0.67 >= 0.5
        assert get_keywords._passes_grounding_gate(phrases, ["python"], [".net"], 0.5) is True

    def test_required_ratio_not_met_fails(self):
        phrases = ["python excel reader", "generic excel tips", "generic csv tips"]
        # 1 of 3 mention "python" -> 0.33 < 0.5
        assert get_keywords._passes_grounding_gate(phrases, ["python"], [".net"], 0.5) is False

    def test_no_required_terms_only_checks_banned(self):
        phrases = ["free mit license", "open source excel library"]
        assert get_keywords._passes_grounding_gate(phrases, [], ["pricing", "subscription"], 0.7) is True

    def test_banned_term_substring_match_is_case_insensitive_via_prelowered_input(self):
        # Callers pass already-lowercased banned terms; the gate lowercases
        # phrases itself, so a mixed-case phrase still matches.
        phrases = ["Aspose.Cells C# Tutorial"]
        assert get_keywords._passes_grounding_gate(phrases, [], ["c#"], 0.7) is False


class TestRegenerateGroundedKeywords:
    """SEO-SCHEMA-A-BARCODE-CELLS-PLATFORM-LICENSE-REMEDIATION: reusable
    grounded regeneration with a verify-and-retry gate, so a future resolver
    for the same defect class (page/font's license.md misrepresentation)
    does not have to reinvent this mechanism from scratch."""

    def _fake_genai(self, monkeypatch, texts):
        """texts: a list of response strings, one per successive call."""
        import types

        calls = {"n": 0}

        class _FakeResponse:
            def __init__(self, text):
                self.text = text

        class _FakeModel:
            def __init__(self, *a, **kw):
                pass

            def generate_content(self, prompt):
                idx = min(calls["n"], len(texts) - 1)
                calls["n"] += 1
                return _FakeResponse(texts[idx])

        fake_genai = types.SimpleNamespace(GenerativeModel=_FakeModel)
        monkeypatch.setitem(sys.modules, "google", types.SimpleNamespace(generativeai=fake_genai))
        monkeypatch.setitem(sys.modules, "google.generativeai", fake_genai)
        monkeypatch.setattr(get_keywords.time, "sleep", lambda *a, **kw: None)
        return calls

    def test_first_attempt_passes_gate_returns_phrases(self, monkeypatch):
        self._fake_genai(monkeypatch, ["python barcode reader\npython qr code generator"])
        result = get_keywords.regenerate_grounded_keywords(
            "How to Render Barcodes", "python", "barcode",
        )
        assert result == ["python barcode reader", "python qr code generator"]

    def test_first_attempt_fails_gate_retries_and_returns_second_attempt(self, monkeypatch):
        calls = self._fake_genai(
            monkeypatch,
            [
                "c# barcode reader\nvb.net qr code generator",  # fails: banned terms present
                "python barcode reader\npython qr code generator",  # passes
            ],
        )
        result = get_keywords.regenerate_grounded_keywords(
            "How to Render Barcodes", "python", "barcode", max_attempts=3,
        )
        assert result == ["python barcode reader", "python qr code generator"]
        assert calls["n"] == 2

    def test_all_attempts_fail_gate_returns_none(self, monkeypatch):
        self._fake_genai(monkeypatch, ["c# barcode reader\nvb.net qr code generator"])
        result = get_keywords.regenerate_grounded_keywords(
            "How to Render Barcodes", "python", "barcode", max_attempts=2,
        )
        assert result is None

    def test_extra_context_and_custom_banned_terms_enforced(self, monkeypatch):
        # A license.md-style regeneration: a "pricing" mention must be
        # rejected even though it isn't in the default platform denylist.
        calls = self._fake_genai(
            monkeypatch,
            [
                "cpp mit license pricing tier",  # fails: custom banned term "pricing"
                "cpp mit license free open source",  # passes
            ],
        )
        result = get_keywords.regenerate_grounded_keywords(
            "License", "cpp", "cells",
            extra_context="This page states the product is MIT licensed and free.",
            required_terms=["license", "mit", "free"],
            banned_terms=list(get_keywords._DEFAULT_PLATFORM_BANNED_TERMS) + ["pricing"],
            max_attempts=3,
        )
        assert result == ["cpp mit license free open source"]
        assert calls["n"] == 2

    def test_gemini_exception_does_not_crash_and_retries(self, monkeypatch):
        import types

        class _FakeModelRaisesOnce:
            _n = {"count": 0}

            def __init__(self, *a, **kw):
                pass

            def generate_content(self, prompt):
                _FakeModelRaisesOnce._n["count"] += 1
                if _FakeModelRaisesOnce._n["count"] == 1:
                    raise RuntimeError("simulated API failure")
                class _R:
                    text = "python barcode reader\npython qr code generator"
                return _R()

        fake_genai = types.SimpleNamespace(GenerativeModel=_FakeModelRaisesOnce)
        monkeypatch.setitem(sys.modules, "google", types.SimpleNamespace(generativeai=fake_genai))
        monkeypatch.setitem(sys.modules, "google.generativeai", fake_genai)
        monkeypatch.setattr(get_keywords.time, "sleep", lambda *a, **kw: None)

        result = get_keywords.regenerate_grounded_keywords(
            "How to Render Barcodes", "python", "barcode", max_attempts=3,
        )
        assert result == ["python barcode reader", "python qr code generator"]

    def test_metrics_recording_exception_never_breaks_regeneration(self, monkeypatch):
        self._fake_genai(monkeypatch, ["python barcode reader\npython qr code generator"])
        monkeypatch.setattr(
            get_keywords.llm_metrics_adapter, "record_gemini_call",
            lambda *a, **kw: (_ for _ in ()).throw(RuntimeError("metrics boom")),
        )
        result = get_keywords.regenerate_grounded_keywords(
            "How to Render Barcodes", "python", "barcode",
        )
        assert result == ["python barcode reader", "python qr code generator"]
