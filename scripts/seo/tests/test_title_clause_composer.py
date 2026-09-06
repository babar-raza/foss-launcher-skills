"""SEO-TITLE-CLAUSE-COMPOSER (v10/v13, Finding #57): LLM-composed,
grounding-verified natural-language title clauses for the three lower
grounding tiers (formats_json, claims_json, curated_keywords).

Acceptance checks mirrored here (per the governing plan's worked taskcard):
  - golden-set-regression-unaffected (via resolve_title_with_composition)
  - fabrication-caught
  - over-length-retries-then-falls-back
  - api-failure-falls-back-cleanly
  - naturalness-gate-catches-awkward-but-grounded
  - cache-prevents-recomposition-on-unchanged-source
Plus both negative controls.
"""
from __future__ import annotations

import json
import sys
from pathlib import Path

import pytest

_SCRIPTS = Path(__file__).resolve().parents[2]
if str(_SCRIPTS) not in sys.path:
    sys.path.insert(0, str(_SCRIPTS))

import seo.pipeline.title_clause_composer as tcc  # noqa: E402
import seo.pipeline.title_templates as tt  # noqa: E402
from seo.pipeline.title_clause_composer import (  # noqa: E402
    TIERS_REQUIRING_COMPOSITION,
    check_enumeration_membership,
    check_grounding_preservation,
    compose_natural_clause,
    normalize_casing,
)


def _clause_response(clause: str) -> str:
    return json.dumps({"clause": clause})


@pytest.fixture(autouse=True)
def _reset(tmp_path):
    tcc.configure()
    yield
    tcc.configure()


# ---------------------------------------------------------------------------
# Scope: which tiers invoke composition at all
# ---------------------------------------------------------------------------


class TestTierScope:
    def test_gsc_query_tier_never_invokes_llm(self, tmp_path):
        def _fail(prompt):
            raise AssertionError("gsc_query must never reach the LLM")

        result = compose_natural_clause(
            "convert pdf to word python", "gsc_query", "pdf", "python", "docs_devguide_index",
            cache_path=tmp_path / "cache.json", llm_call=_fail,
        )
        assert result == "convert pdf to word python"

    def test_description_tier_never_invokes_llm(self, tmp_path):
        def _fail(prompt):
            raise AssertionError("description must never reach the LLM")

        result = compose_natural_clause(
            "A real, already-verified description.", "description", "pdf", "python", "docs_devguide_index",
            cache_path=tmp_path / "cache.json", llm_call=_fail,
        )
        assert result == "A real, already-verified description."

    def test_all_three_lower_tiers_are_in_scope(self):
        assert TIERS_REQUIRING_COMPOSITION == {"formats_json", "claims_json", "curated_keywords"}

    def test_no_raw_source_text_returns_none(self, tmp_path):
        result = compose_natural_clause(
            None, "formats_json", "pdf", "python", "docs_devguide_index",
            cache_path=tmp_path / "cache.json", llm_call=lambda p: (_ for _ in ()).throw(AssertionError()),
        )
        assert result is None


# ---------------------------------------------------------------------------
# Success path
# ---------------------------------------------------------------------------


class TestSuccessPath:
    def test_grounded_llm_response_is_composed_and_normalized(self, tmp_path):
        result = compose_natural_clause(
            "Supports Pdf, Docx, Xlsx export formats", "formats_json", "pdf", "python", "docs_devguide_index",
            cache_path=tmp_path / "cache.json",
            llm_call=lambda p: _clause_response("pdf and docx conversion support"),
        )
        assert result == "Pdf And Docx Conversion Support"


# ---------------------------------------------------------------------------
# Acceptance check: fabrication-caught
# ---------------------------------------------------------------------------


class TestFabricationCaught:
    def test_off_topic_response_rejected_by_grounding_preservation(self, tmp_path):
        """A mocked, fabricated/off-topic Gemini response is rejected by the
        grounding-preservation (token-overlap) check, not silently accepted."""
        result = compose_natural_clause(
            "supports pdf and docx export", "claims_json", "pdf", "python", "docs_devguide_index",
            cache_path=tmp_path / "cache.json",
            llm_call=lambda p: _clause_response("Free Online Video Converter Tool"),
        )
        assert result is None

    def test_check_grounding_preservation_unit(self):
        assert check_grounding_preservation("Pdf Docx Conversion", "supports pdf and docx export")
        assert not check_grounding_preservation("Totally Unrelated Words", "supports pdf and docx export")

    def test_short_raw_source_uses_scaled_down_bar(self):
        """A single-token raw source (e.g. one format name) cannot clear a
        literal 2-token bar through no fault of a faithful composition --
        the bar scales to min(2, len(raw_tokens))."""
        assert check_grounding_preservation("Glb Format Support", "glb")
        assert not check_grounding_preservation("Totally Different Word", "glb")


# ---------------------------------------------------------------------------
# SEO-CHECK-GROUNDING-PRESERVATION-ENTITY-COVERAGE-RESOLVER-1: per-entity
# enumeration membership (safety-critical -- discovered live, real
# fabricated "SVG" export format riding along with 6 real ones)
# ---------------------------------------------------------------------------


class TestCheckEnumerationMembership:
    _REAL_FORMATS = {"ppt", "pdf", "xps", "pptx", "ppsx", "tiff", "odp", "html"}

    def test_reproduces_the_real_svg_fabrication_and_rejects_it(self):
        """Exact real candidate that passed check_grounding_preservation for
        SaveFormat.md (it-0055) -- 6 real formats + 1 fabricated ("SVG",
        confirmed absent from claims.json and formats.json) closed with a
        generic "and other formats" wrap-up. Must now be rejected."""
        composed = (
            "Explore the SaveFormat enum in Aspose.Slides FOSS for .NET, "
            "enabling export of presentations to PPT, PDF, XPS, PPTX, HTML, "
            "SVG and other formats."
        )
        assert not check_enumeration_membership(composed, self._REAL_FORMATS)

    def test_all_real_enumeration_passes(self):
        composed = "Exports to PPT, PDF, XPS, PPTX, HTML and other formats."
        assert check_enumeration_membership(composed, self._REAL_FORMATS)

    def test_oxford_comma_all_real_enumeration_passes(self):
        composed = "Exports to PPT, PDF, and XPS for archival."
        assert check_enumeration_membership(composed, self._REAL_FORMATS)

    def test_fabricated_last_item_before_and_is_caught(self):
        composed = "Exports to PPT, PDF, and FAKE for archival."
        assert not check_enumeration_membership(composed, self._REAL_FORMATS)

    def test_single_fabricated_item_with_no_enumeration_syntax_is_still_caught(self):
        """A single ALL-CAPS candidate token is checked unconditionally --
        no comma/and-or list is needed to trigger the check at all, since
        detection is position-independent, not run-based."""
        composed = "Exports to FAKE for archival purposes."
        assert not check_enumeration_membership(composed, self._REAL_FORMATS)

    def test_two_item_list_is_still_checked(self):
        """Unlike the reworked-away syntactic run-detector, a 2-item list
        is fully checked too -- detection no longer depends on run length
        at all, only on the ALL-CAPS shape of each candidate."""
        composed = "Exports to PPT, FAKE for testing."
        assert not check_enumeration_membership(composed, self._REAL_FORMATS)

    def test_ordinary_prose_with_no_unusual_tokens_never_flagged(self):
        """Plain prose built entirely from common words (plus the
        universally-exempt "Aspose"/"enum") never trips the check, however
        many short candidate-shaped tokens it contains."""
        composed = "Learn about the SaveFormat enum in Aspose for the library today."
        assert check_enumeration_membership(composed, self._REAL_FORMATS)

    def test_common_wrap_up_words_never_flagged(self):
        """"other"/"useful"/"formats"/"today" are ordinary common English
        words (or, for "formats", simply too long to match the candidate
        regex) -- never flagged regardless of casing or position."""
        composed = "Exports to PPT, PDF, XPS and other useful formats today."
        assert check_enumeration_membership(composed, self._REAL_FORMATS)

    def test_empty_vocabulary_fails_any_all_caps_candidate_closed(self):
        composed = "Exports to PPT for archival."
        assert not check_enumeration_membership(composed, set())

    def test_no_all_caps_tokens_passes_regardless_of_vocabulary(self):
        assert check_enumeration_membership("A short natural clause.", set())

    def test_lowercase_and_pascal_case_format_mentions_are_checked_too(self):
        """Rework 2 (round-2 review fix): detection is case-insensitive --
        a fabricated format written in lowercase or PascalCase (matching
        formats.json's own convention) is checked exactly like an ALL-CAPS
        one, not silently exempted by casing alone."""
        assert check_enumeration_membership("Exports to ppt, pdf and xps for archival.", self._REAL_FORMATS)
        assert check_enumeration_membership("Exports to Ppt, Pdf and Xps for archival.", self._REAL_FORMATS)
        assert not check_enumeration_membership("Exports to ppt, pdf and fake for archival.", self._REAL_FORMATS)
        assert not check_enumeration_membership("Exports to Ppt, Pdf and Fake for archival.", self._REAL_FORMATS)

    def test_universal_exempt_acronym_never_checked(self):
        composed = "Built on the Aspose FOSS SDK API for real projects."
        assert check_enumeration_membership(composed, set())

    def test_caller_supplied_exempt_token_never_checked(self):
        composed = "Available for the CPP platform today."
        assert not check_enumeration_membership(composed, set())  # CPP not exempt by default
        assert check_enumeration_membership(composed, set(), exempt={"cpp"})

    def test_net_is_no_longer_globally_exempt(self):
        """Round-2 review finding: "NET" used to sit on the STATIC
        universal exempt list, exempting it on every page regardless of
        that page's actual platform. It must now only be exempt when the
        caller explicitly supplies it (e.g. description_composer.py passing
        the current page's own platform)."""
        composed = "Available for the NET platform today."
        assert not check_enumeration_membership(composed, set())
        assert check_enumeration_membership(composed, set(), exempt={"net"})

    def test_digit_leading_fabricated_token_is_still_checked(self):
        """Round-1 review secondary finding: the original leading-letter-
        required regex mis-tokenized "3DS", accidentally evading detection
        entirely. The reworked candidate regex has no such requirement."""
        composed = "Exports to PPT, PDF, XPS and 3DS for archival."
        assert not check_enumeration_membership(composed, self._REAL_FORMATS)

    def test_digit_leading_real_token_passes_when_in_vocabulary(self):
        composed = "Exports to PPT and 3DS for archival."
        assert check_enumeration_membership(composed, self._REAL_FORMATS | {"3ds"})


# ---------------------------------------------------------------------------
# Round-1 independent review REJECT (agentId a4a1df659bd8597df): 3 real,
# live-reproduced bypasses of the original syntax-based run-detector, all
# plausible natural LLM phrasings. Locked in as permanent regression tests.
# ---------------------------------------------------------------------------


class TestEnumerationMembershipRound1BypassesFixed:
    _REAL_FORMATS = {"ppt", "pdf", "xps", "pptx", "html"}

    def test_bypass_1_terminator_then_non_comma_joined_trailing_fabrication(self):
        """"...and other formats like SVG." -- SVG previously evaded
        detection entirely because it was never comma/and-or-joined to
        anything after the terminator "other" closed the run."""
        composed = "Exports to PPT, PDF, XPS and other formats like SVG."
        assert not check_enumeration_membership(composed, self._REAL_FORMATS)

    def test_bypass_1_variant_including_phrasing(self):
        composed = "Exports to PPT, PDF, XPS and other formats, including SVG."
        assert not check_enumeration_membership(composed, self._REAL_FORMATS)

    def test_bypass_2_enumeration_split_across_a_sentence_boundary(self):
        """"PPT and PDF. Also supports XPS and SVG." -- "Also" was itself a
        terminator, splitting one real+fabricated set into two sub-3
        fragments neither of which reached the old run-length-3 threshold."""
        composed = "Supports PPT and PDF. Also supports XPS and SVG."
        assert not check_enumeration_membership(composed, self._REAL_FORMATS)

    def test_bypass_3_vocabulary_never_contaminated_by_grounding_text(self):
        """check_enumeration_membership itself takes real_vocabulary as an
        explicit parameter -- this proves the FUNCTION treats whatever
        vocabulary it is given as authoritative (expected: real_vocabulary
        is the caller's sole responsibility, this function has no opinion
        on where it came from). The actual fix for bypass 3 is that
        description_composer.py's call site sources real_vocabulary only
        from formats.json (rework 3: not even claims text -- round-3 review
        found that also unsound), never from grounded_keyword_signal or
        current_description -- see
        test_description_composer.py::TestEnumerationMembershipEndToEnd::
        test_bypass_3_keyword_signal_mentioning_the_fabrication_does_not_
        ground_it for the real, end-to-end, non-contamination proof
        (round-2 review finding: this proof was missing from rework 1)."""
        composed = "Exports to PPT, PDF, XPS and SVG for archival."
        # A vocabulary that (incorrectly, hypothetically) included "svg"
        # would of course pass -- the real fix is description_composer.py
        # never building such a vocabulary from untrusted grounding text.
        assert check_enumeration_membership(composed, self._REAL_FORMATS | {"svg"})
        assert not check_enumeration_membership(composed, self._REAL_FORMATS)


class TestEnumerationMembershipRound3FormatCollisionWordsFixed:
    """Round-3 independent review (agentId ab143c9e5f0654f34) REJECT:
    _ENUM_COMMON_WORDS used to blanket-exempt words that are ALSO real,
    functional format members for at least one real family (confirmed
    live: "doc" is a real SaveFormat member for words/python). The
    exemption was family-blind, so a fabricated claim of one of these
    words on an UNRELATED family was never checked. Removed from the
    common-word list; now checked normally against each page's own real,
    family-scoped vocabulary like any other candidate."""

    def test_previously_exempt_collision_word_is_now_checked_normally(self):
        # "doc" is no longer blanket-exempt -- with no real vocabulary
        # containing it, a bare mention now correctly fails closed.
        assert not check_enumeration_membership("Exports to DOC for archival.", set())
        assert not check_enumeration_membership("Exports to TEXT for archival.", set())

    def test_collision_word_still_passes_when_genuinely_real_for_this_family(self):
        # On the one real family where "doc" genuinely is a member, it
        # still passes -- the fix routes it through the normal, correct,
        # family-scoped real_vocabulary check instead of a blanket global
        # exemption, it does not turn "doc" into something always rejected.
        assert check_enumeration_membership("Exports to DOC for archival.", {"doc"})

    def test_collision_word_fabricated_on_an_unrelated_family_is_caught(self):
        """The exact class of live bypass round 3 found: "DOC" fabricated
        on a family whose own real vocabulary has no such member."""
        real_3d_formats = {"obj", "fbx", "stl", "gltf"}
        composed = "Convert 3D models exporting to OBJ, FBX, STL, glTF, DOC and other formats today."
        assert not check_enumeration_membership(composed, real_3d_formats)


# ---------------------------------------------------------------------------
# Acceptance check: over-length-retries-then-falls-back
# ---------------------------------------------------------------------------


class TestOverLengthRetry:
    def test_over_length_retries_once_then_falls_back(self, tmp_path):
        calls = {"n": 0}

        def _always_too_long(prompt):
            calls["n"] += 1
            return _clause_response("This Is Way Too Many Words For A Title Clause Honestly")

        result = compose_natural_clause(
            "supports many formats for conversion", "formats_json", "pdf", "python", "docs_devguide_index",
            cache_path=tmp_path / "cache.json", llm_call=_always_too_long,
        )
        assert result is None
        assert calls["n"] == 2, "exactly one retry (2 total calls), never more"

    def test_over_length_then_correct_on_retry_succeeds(self, tmp_path):
        calls = {"n": 0}

        def _second_call_ok(prompt):
            calls["n"] += 1
            if calls["n"] == 1:
                return _clause_response("This Is Way Too Many Words For A Title Clause Honestly")
            return _clause_response("pdf docx conversion support")

        result = compose_natural_clause(
            "supports pdf and docx conversion", "formats_json", "pdf", "python", "docs_devguide_index",
            cache_path=tmp_path / "cache.json", llm_call=_second_call_ok,
        )
        assert result == "Pdf Docx Conversion Support"
        assert calls["n"] == 2

    def test_never_truncates_mid_phrase(self, tmp_path):
        """A fallback (None) must never be a truncated version of the
        over-length response -- only the caller's own fallback_skeleton
        path handles this, never a mid-phrase cut here."""
        result = compose_natural_clause(
            "supports many formats", "formats_json", "pdf", "python", "docs_devguide_index",
            cache_path=tmp_path / "cache.json",
            llm_call=lambda p: _clause_response("One Two Three Four Five Six Seven Eight"),
        )
        assert result is None


# ---------------------------------------------------------------------------
# Acceptance check: api-failure-falls-back-cleanly
# ---------------------------------------------------------------------------


class TestApiFailureFallback:
    def test_exception_falls_back_cleanly_never_raises(self, tmp_path):
        def _raise(prompt):
            raise RuntimeError("429 quota exceeded")

        result = compose_natural_clause(
            "supports pdf export", "formats_json", "pdf", "python", "docs_devguide_index",
            cache_path=tmp_path / "cache.json", llm_call=_raise,
        )
        assert result is None

    def test_none_response_falls_back(self, tmp_path):
        result = compose_natural_clause(
            "supports pdf export", "formats_json", "pdf", "python", "docs_devguide_index",
            cache_path=tmp_path / "cache.json", llm_call=lambda p: None,
        )
        assert result is None

    def test_non_json_non_empty_response_is_tolerated_as_bare_string(self, tmp_path):
        """Some models ignore the 'respond with JSON' instruction for a
        one-key response -- a bare string reply must still work, not crash."""
        result = compose_natural_clause(
            "supports pdf export", "formats_json", "pdf", "python", "docs_devguide_index",
            cache_path=tmp_path / "cache.json", llm_call=lambda p: "pdf export support",
        )
        assert result == "Pdf Export Support"

    def test_markdown_fenced_json_response_is_stripped_and_parsed(self, tmp_path):
        """Regression pin (found live, it-0026 real evidence run): Gemini
        commonly wraps its JSON reply in a ```json ... ``` fence -- an
        un-stripped fence made json.loads() fail every real call, silently
        falling through to the bare-string branch and treating the whole
        fenced blob (markers included) as the clause -- never valid."""
        fenced = '```json\n{\n  "clause": "Supports CDR CGM Encryption HTML Markdown"\n}\n```'
        result = compose_natural_clause(
            "Supports Cdr, Cgm, Encryption, Html, Markdown, Ofd formats",
            "formats_json", "pdf", "python", "docs_devguide_index",
            cache_path=tmp_path / "cache.json", llm_call=lambda p: fenced,
        )
        assert result == "Supports CDR CGM Encryption HTML Markdown"

    def test_bare_fence_without_json_language_tag_is_also_stripped(self, tmp_path):
        fenced = '```\n{"clause": "pdf export support"}\n```'
        result = compose_natural_clause(
            "supports pdf export", "formats_json", "pdf", "python", "docs_devguide_index",
            cache_path=tmp_path / "cache.json", llm_call=lambda p: fenced,
        )
        assert result == "Pdf Export Support"


# ---------------------------------------------------------------------------
# Acceptance check: naturalness-gate-catches-awkward-but-grounded
# ---------------------------------------------------------------------------


class TestNaturalnessGate:
    def test_keyword_list_shaped_clause_is_caught_despite_passing_grounding(self, tmp_path):
        """A synthetic clause that passes grounding-preservation but reads
        as a keyword list is caught by Contract D's naturalness evaluator
        and falls back -- a real adversarial test, not a passing-case-only
        demonstration."""
        result = compose_natural_clause(
            "pdf docx xlsx conversion tool", "curated_keywords", "pdf", "python", "docs_devguide_index",
            cache_path=tmp_path / "cache.json",
            llm_call=lambda p: _clause_response("Pdf, Docx, Xlsx, Free Tool"),
        )
        assert result is None

    def test_all_lowercase_response_is_fixed_by_casing_normalization_not_naturalness(self, tmp_path):
        """normalize_casing runs before the naturalness check -- a plain
        all-lowercase response is a normalization case, not a naturalness
        failure, and should succeed once cased."""
        result = compose_natural_clause(
            "export pdf files quickly and reliably", "curated_keywords", "pdf", "python", "docs_devguide_index",
            cache_path=tmp_path / "cache.json",
            llm_call=lambda p: _clause_response("export pdf files quickly"),
        )
        assert result == "Export Pdf Files Quickly"


class TestNormalizeCasing:
    def test_title_cases_normal_words(self):
        assert normalize_casing("pdf export support") == "Pdf Export Support"

    def test_preserves_existing_acronyms(self):
        assert normalize_casing("PDF and API support") == "PDF And API Support"


# ---------------------------------------------------------------------------
# Acceptance check: cache-prevents-recomposition-on-unchanged-source
# ---------------------------------------------------------------------------


class TestCaching:
    def test_second_call_with_unchanged_source_is_a_cache_hit(self, tmp_path):
        calls = {"n": 0}

        def _judge(prompt):
            calls["n"] += 1
            return _clause_response("pdf and docx conversion support")

        cache_path = tmp_path / "cache.json"
        first = compose_natural_clause(
            "supports pdf and docx export", "formats_json", "pdf", "python", "docs_devguide_index",
            cache_path=cache_path, llm_call=_judge,
        )
        second = compose_natural_clause(
            "supports pdf and docx export", "formats_json", "pdf", "python", "docs_devguide_index",
            cache_path=cache_path, llm_call=_judge,
        )
        assert first == second
        assert calls["n"] == 1, "second call with unchanged source must be a cache hit, zero new LLM calls"

    def test_changed_source_text_is_not_a_cache_hit(self, tmp_path):
        calls = {"n": 0}

        def _judge(prompt):
            calls["n"] += 1
            return _clause_response("pdf and docx conversion support")

        cache_path = tmp_path / "cache.json"
        compose_natural_clause(
            "supports pdf and docx export", "formats_json", "pdf", "python", "docs_devguide_index",
            cache_path=cache_path, llm_call=_judge,
        )
        compose_natural_clause(
            "supports pdf and xlsx export", "formats_json", "pdf", "python", "docs_devguide_index",
            cache_path=cache_path, llm_call=_judge,
        )
        assert calls["n"] == 2

    def test_a_fallen_back_composition_is_never_cached(self, tmp_path):
        """Only approved compositions are cached -- a transient API failure
        must not be memorized as a permanent failure; a later run with the
        same source should try again, not silently reuse a None forever."""
        cache_path = tmp_path / "cache.json"
        calls = {"n": 0}

        def _fail_then_succeed(prompt):
            calls["n"] += 1
            if calls["n"] == 1:
                raise RuntimeError("transient failure")
            return _clause_response("pdf and docx conversion support")

        first = compose_natural_clause(
            "supports pdf and docx export", "formats_json", "pdf", "python", "docs_devguide_index",
            cache_path=cache_path, llm_call=_fail_then_succeed,
        )
        assert first is None
        second = compose_natural_clause(
            "supports pdf and docx export", "formats_json", "pdf", "python", "docs_devguide_index",
            cache_path=cache_path, llm_call=_fail_then_succeed,
        )
        assert second == "Pdf And Docx Conversion Support"
        assert calls["n"] == 2


# ---------------------------------------------------------------------------
# Acceptance check: golden-set-regression-unaffected (title_templates.py integration)
# ---------------------------------------------------------------------------


class TestResolveTitleWithCompositionIntegration:
    def _registry(self):
        return {
            "max_content_clause_words": 6,
            "page_types": {
                "docs_devguide_index": {
                    "rigid": False,
                    "skeleton": "Aspose.{Family} FOSS for {Platform} — {ContentClause}",
                    "fallback_skeleton": "Aspose.{Family} FOSS for {Platform} — Developer Guide",
                },
                "kb_faq": {
                    "rigid": True,
                    "fallback_skeleton": "Aspose.{Family} FOSS — Frequently Asked Questions",
                },
            },
        }

    def test_golden_set_regression_no_raw_source_text_is_byte_identical_to_resolve_title(self):
        """The 2 already-shipped devguide titles resolved via gsc_query/
        description with no composition step at all in the old code path --
        a caller that doesn't pass raw_source_text/source_tier must render
        byte-identical to plain resolve_title()."""
        registry = self._registry()
        old = tt.resolve_title(
            "docs_devguide_index", family="PDF", platform="Python",
            content_clause="Convert PDF To Word", registry=registry,
        )
        new = tt.resolve_title_with_composition(
            "docs_devguide_index", family="PDF", platform="Python",
            raw_source_text="Convert PDF To Word", source_tier=None, registry=registry,
        )
        assert old == new

    def test_rigid_page_type_never_calls_compose_fn(self):
        def _fail(*a, **kw):
            raise AssertionError("rigid page types must never compose")

        result = tt.resolve_title_with_composition(
            "kb_faq", family="PDF", raw_source_text="something",
            source_tier="curated_keywords", registry=self._registry(), compose_fn=_fail,
        )
        assert result == "Aspose.PDF FOSS — Frequently Asked Questions"

    def test_lower_tier_routes_through_compose_fn(self):
        captured = {}

        def _fake_compose(raw_source_text, source_tier, family, platform, page_type, *, max_words):
            captured["args"] = (raw_source_text, source_tier, family, platform, page_type, max_words)
            return "Composed Clause"

        result = tt.resolve_title_with_composition(
            "docs_devguide_index", family="PDF", platform="Python",
            raw_source_text="raw text", source_tier="formats_json",
            registry=self._registry(), compose_fn=_fake_compose,
        )
        assert result == "Aspose.PDF FOSS for Python — Composed Clause"
        assert captured["args"] == ("raw text", "formats_json", "PDF", "Python", "docs_devguide_index", 6)

    def test_compose_fn_returning_none_falls_back_to_skeleton_only(self):
        result = tt.resolve_title_with_composition(
            "docs_devguide_index", family="PDF", platform="Python",
            raw_source_text="raw text", source_tier="formats_json",
            registry=self._registry(), compose_fn=lambda *a, **kw: None,
        )
        assert result == "Aspose.PDF FOSS for Python — Developer Guide"
