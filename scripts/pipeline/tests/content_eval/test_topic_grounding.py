"""Tests for the topic_grounding evaluator (CE-02, gap G-03).

Real-fixture tests (no monkeypatching, real knowledge/ tree):
  - The 4 pages retired in commit 820d2c7e8e must FAIL -- the false-negative
    regression guard. Fixtures live under
    scripts/pipeline/tests/content_eval/fixtures/kb.aspose.org/en/{family}/
    {platform}/, the nested path shape CE-01 proved is required for
    Page._infer_metadata() to infer family/platform/subdomain correctly.
  - At least 2 real, legitimate `type: topic` how-to pages from the current
    corpus must NOT FAIL -- the false-positive regression guard (mandatory
    per the taskcard's own acceptance checks, not optional).
  - One real `faq.md` page is kept only as a non-crash shape smoke test --
    its `evidence.claims`/`apis` are non-empty, so it never exercises the
    noun-extraction/overlap logic at all (see this taskcard's
    pre-implementation design note on why faq.md is a weak negative
    control).

Unit tests use configure(knowledge_root=tmp_path) with small synthetic
claims.json/api_surface.json fixtures to exercise the two specific
false-negative traps found during design validation directly, independent
of the real corpus's own evolving data.
"""

from __future__ import annotations

import json
from pathlib import Path

from content_eval.evaluators import topic_grounding as tg
from content_eval.models import Page

_REPO_ROOT = Path(__file__).resolve().parents[4]
_FIXTURES = _REPO_ROOT / "scripts/pipeline/tests/content_eval/fixtures/kb.aspose.org/en"
_REAL_CONTENT = _REPO_ROOT / "content/kb.aspose.org/en"


def _load_real(path: Path) -> Page:
    return Page.load(path)


class TestTopicGroundingRealFixtures:
    """False-negative regression guard: the 4 retired fixtures must FAIL."""

    def setup_method(self):
        self.evaluator = tg.TopicGroundingEvaluator()

    def _assert_fails(self, relpath: str):
        page = _load_real(_FIXTURES / relpath)
        findings = self.evaluator.evaluate(page, None)
        tg_findings = [f for f in findings if f.category == "TG"]
        assert len(tg_findings) == 1, (
            f"expected exactly one TG finding for {relpath}, got {findings}"
        )
        assert tg_findings[0].level == "FAIL"
        assert tg_findings[0].evaluator == "topic_grounding"

    def test_onestore_format_fails(self):
        """Highest-risk case: OneStore parsing genuinely exists in
        note/python's codebase (46+ claims, a real parse_onestore_file API
        entry) but only as reachable=false internal implementation -- a
        naive (non-reachability-aware) overlap check would NOT fail this."""
        self._assert_fails("note/python/how-to-convert-onestore-format-python.md")

    def test_scene_entities_fails(self):
        self._assert_fails("note/python/how-to-build-scene-entities-python.md")

    def test_compound_file_cpp_fails(self):
        self._assert_fails("email/cpp/how-to-load-compound-file-cpp.md")

    def test_compound_file_dotnet_fails(self):
        self._assert_fails("email/net/how-to-load-compound-file-dotnet.md")


class TestTopicGroundingRealNegativeControls:
    """False-positive regression guard: real, evidence-backed how-to pages
    must not FAIL. Mandatory per the taskcard's acceptance checks."""

    def setup_method(self):
        self.evaluator = tg.TopicGroundingEvaluator()

    def _assert_no_fail(self, path: Path):
        page = _load_real(path)
        findings = self.evaluator.evaluate(page, None)
        fails = [f for f in findings if f.level == "FAIL"]
        assert not fails, f"unexpected FAIL for {path}: {fails}"

    def test_3d_java_convert_models_no_fail(self):
        self._assert_no_fail(_REAL_CONTENT / "3d/java/how-to-convert-3d-models-java.md")

    def test_cells_java_load_spreadsheet_no_fail(self):
        self._assert_no_fail(_REAL_CONTENT / "cells/java/how-to-load-spreadsheet-java.md")

    def test_csv_to_json_conversion_no_fail(self):
        """Portfolio dry run (2026-09-18) initially FAILed this real page:
        no single class is named "CsvToJson", even though CSV
        (CSVLoadOptions/CSVSaveOptions) and JSON (JsonSaveOptions/
        JsonHandler) are each independently real and reachable. Regression
        guard for the connector-word segment-splitting fix."""
        self._assert_no_fail(_REAL_CONTENT / "cells/python/how-to-convert-csv-to-json-python.md")

    def test_eml_to_msg_conversion_no_fail(self):
        """Same shape as the CSV/JSON case: EML (mapi_message.load_from_eml)
        and MSG are each independently real for email/cpp."""
        self._assert_no_fail(_REAL_CONTENT / "email/cpp/how-to-convert-eml-to-msg-cpp.md")

    def test_faq_page_shape_smoke_test(self):
        """FAQ pages are `type: topic` but not `how-to-*` shaped -- the
        evaluator must not crash and must not FAIL, but this does NOT
        exercise the noun-extraction/overlap logic (evidence is non-empty,
        so the empty-evidence short-circuit fires first)."""
        self._assert_no_fail(_REAL_CONTENT / "3d/java/faq.md")


class TestTopicGroundingRobustness:
    def setup_method(self):
        self.evaluator = tg.TopicGroundingEvaluator()

    def teardown_method(self):
        tg.configure()  # reset to real knowledge/ tree

    def test_no_knowledge_at_all_returns_empty(self, tmp_path):
        """A pre-launch family with no claims.json/api_surface.json at all
        must be skipped cleanly (return []), not raise -- taskcard
        robustness rule."""
        tg.configure(knowledge_root=tmp_path)
        page = Page.load(_FIXTURES / "note/python/how-to-convert-onestore-format-python.md")
        findings = self.evaluator.evaluate(page, None)
        assert findings == []

    def test_non_topic_page_returns_empty(self):
        page = _load_real(_REAL_CONTENT / "3d/java/faq.md")
        page.frontmatter["type"] = "docs"
        assert self.evaluator.evaluate(page, None) == []


class TestSplitIdentifier:
    def test_camel_case(self):
        assert tg._split_identifier("CompoundFile") == frozenset({"compound", "file"})
        assert tg._split_identifier("OneStoreFile") == frozenset({"one", "store", "file"})

    def test_snake_case(self):
        assert tg._split_identifier("parse_onestore_file") == frozenset({"parse", "onestore", "file"})

    def test_single_word(self):
        assert tg._split_identifier("Mesh") == frozenset({"mesh"})


class TestExtractTopicNoun:
    def test_strips_verb_and_platform_suffix(self):
        assert tg._extract_topic_noun("how-to-convert-onestore-format-python", "python") == "onestore-format"

    def test_non_howto_slug_returns_none(self):
        assert tg._extract_topic_noun("faq", "python") is None

    def test_no_matching_verb_keeps_full_inner(self):
        # No verb keyword matches "frobnicate-widget" -- noun falls back to
        # the full inner string rather than raising or dropping a word.
        assert tg._extract_topic_noun("how-to-frobnicate-widget-python", "python") == "frobnicate-widget"


class TestNounSegments:
    def test_connector_splits_into_independent_segments(self):
        assert tg._noun_segments("csv-to-json") == [frozenset({"csv"}), frozenset({"json"})]

    def test_no_connector_stays_one_segment(self):
        assert tg._noun_segments("onestore-format") == [frozenset({"onestore", "format"})]
        assert tg._noun_segments("compound-file") == [frozenset({"compound", "file"})]

    def test_degenerate_leading_connector_falls_back_safely(self):
        """A connector at the boundary must never produce an empty segment
        (an empty frozenset is a subset of everything, which would
        trivially "ground" any candidate) -- falls back to whole-noun
        matching instead."""
        assert tg._noun_segments("to-json") == [frozenset({"json"})]

    def test_all_stopwords_returns_no_segments(self):
        assert tg._noun_segments("to") == []


class TestGroundedFalseNegativeTraps:
    """Directly exercises the two false-negative traps found during design
    validation, against small synthetic fixtures -- independent of the real
    corpus's own evolving data."""

    def setup_method(self):
        self.evaluator = tg.TopicGroundingEvaluator()

    def teardown_method(self):
        tg.configure()

    def _write_knowledge(self, tmp_path: Path, family: str, platform: str,
                          classes: list[dict], claims: list[dict]):
        merged = tmp_path / family / platform / "merged"
        merged.mkdir(parents=True)
        (merged / "api_surface.json").write_text(json.dumps(classes), encoding="utf-8")
        (merged / "claims.json").write_text(json.dumps(claims), encoding="utf-8")
        tg.configure(knowledge_root=tmp_path)

    def test_unreachable_class_does_not_ground(self, tmp_path):
        """An unreachable OneStoreFile-shaped class must NOT ground the
        'onestore-format' topic, even though its name substring-contains
        'onestore' after camelCase splitting."""
        self._write_knowledge(
            tmp_path, "note", "python",
            classes=[{
                "name": "OneStoreFile", "reachable": False,
                "methods": [], "properties": [], "enum_members": [],
            }],
            claims=[{
                "claim_id": "CLM-1", "kind": "api_class",
                "text": "Class OneStoreFile defined in parser.py",
            }],
        )
        page = Page.load(_FIXTURES / "note/python/how-to-convert-onestore-format-python.md")
        findings = self.evaluator.evaluate(page, None)
        assert any(f.level == "FAIL" for f in findings)

    def test_reachable_but_partial_word_match_does_not_ground(self, tmp_path):
        """A REACHABLE FileFormat class must not ground 'onestore-format'
        via the single shared word 'format' -- full noun word-set coverage
        is required, not single-word overlap."""
        self._write_knowledge(
            tmp_path, "note", "python",
            classes=[{
                "name": "FileFormat", "reachable": True,
                "methods": [], "properties": [], "enum_members": [],
            }],
            claims=[],
        )
        page = Page.load(_FIXTURES / "note/python/how-to-convert-onestore-format-python.md")
        findings = self.evaluator.evaluate(page, None)
        assert any(f.level == "FAIL" for f in findings)

    def test_reachable_full_match_grounds(self, tmp_path):
        """A REACHABLE class whose full word-set covers the noun DOES
        ground the topic -- positive control for the matching logic itself."""
        self._write_knowledge(
            tmp_path, "email", "cpp",
            classes=[{
                "name": "CompoundFile", "reachable": True,
                "methods": [], "properties": [], "enum_members": [],
            }],
            claims=[],
        )
        page = Page.load(_FIXTURES / "email/cpp/how-to-load-compound-file-cpp.md")
        findings = self.evaluator.evaluate(page, None)
        assert findings == []
