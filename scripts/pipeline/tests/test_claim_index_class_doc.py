"""Tests for _claim_index.py's class/interface docstring claim augmentation.

Root cause: claims.json only records mechanical signature facts ("Class X
defined in Y.cs", "X.Y property of type Z"), never a class's own descriptive
docstring text. Reference pages' Overview sections quote or paraphrase that
docstring directly, so prose-grounding evaluators (prose_claim_binding,
prose_truth, prose_grounding) had no real claim to trace that prose to --
matching only succeeded by incidental token overlap with unrelated signature
claims, which is unreliable (fails for interfaces with few methods, or any
class whose docstring shares little vocabulary with its own member names).

This synthesizes a claim per class/interface from api_surface.json's `doc`
field, merged into the same claims list every prose-grounding evaluator reads.
"""

from __future__ import annotations

import json

import pytest

from content_eval.evaluators import _claim_index as ci


@pytest.fixture(autouse=True)
def _clear_cache():
    ci.clear_claim_cache()
    yield
    ci.clear_claim_cache()


def _write_knowledge(tmp_path, family="words", platform="net",
                      claims=None, api_surface=None):
    merged = tmp_path / family / platform / "merged"
    merged.mkdir(parents=True)
    (merged / "claims.json").write_text(
        json.dumps(claims if claims is not None else []), encoding="utf-8"
    )
    if api_surface is not None:
        (merged / "api_surface.json").write_text(
            json.dumps(api_surface), encoding="utf-8"
        )
    return merged


class TestLoadClassDocClaims:

    def test_no_api_surface_file_returns_empty(self, tmp_path, monkeypatch):
        monkeypatch.setattr(ci, "KNOWLEDGE_ROOT", tmp_path)
        _write_knowledge(tmp_path, claims=[])
        assert ci._load_class_doc_claims("words", "net") == []

    def test_class_with_doc_becomes_claim(self, tmp_path, monkeypatch):
        monkeypatch.setattr(ci, "KNOWLEDGE_ROOT", tmp_path)
        _write_knowledge(tmp_path, api_surface=[
            {"name": "OptionButtonControl", "doc": "Enables a single choice."},
        ])
        claims = ci._load_class_doc_claims("words", "net")
        assert len(claims) == 1
        assert claims[0]["kind"] == "class_doc"
        assert "OptionButtonControl" in claims[0]["text"]
        assert "Enables a single choice." in claims[0]["text"]

    def test_class_without_doc_skipped(self, tmp_path, monkeypatch):
        monkeypatch.setattr(ci, "KNOWLEDGE_ROOT", tmp_path)
        _write_knowledge(tmp_path, api_surface=[
            {"name": "NoDocClass", "doc": ""},
            {"name": "NoDocClass2"},
        ])
        assert ci._load_class_doc_claims("words", "net") == []

    def test_malformed_api_surface_returns_empty(self, tmp_path, monkeypatch):
        monkeypatch.setattr(ci, "KNOWLEDGE_ROOT", tmp_path)
        merged = tmp_path / "words" / "net" / "merged"
        merged.mkdir(parents=True)
        (merged / "api_surface.json").write_text("not json{{{", encoding="utf-8")
        assert ci._load_class_doc_claims("words", "net") == []

    def test_non_list_api_surface_returns_empty(self, tmp_path, monkeypatch):
        monkeypatch.setattr(ci, "KNOWLEDGE_ROOT", tmp_path)
        merged = tmp_path / "words" / "net" / "merged"
        merged.mkdir(parents=True)
        (merged / "api_surface.json").write_text(
            json.dumps({"classes": []}), encoding="utf-8"
        )
        assert ci._load_class_doc_claims("words", "net") == []


class TestLoadClaimsAugmentation:

    def test_merges_real_claims_and_class_doc_claims(self, tmp_path, monkeypatch):
        monkeypatch.setattr(ci, "KNOWLEDGE_ROOT", tmp_path)
        real_claim = {
            "claim_id": "CLM-words-1",
            "kind": "api_method",
            "text": "OptionButtonControl.Selected property of type bool",
        }
        _write_knowledge(
            tmp_path,
            claims=[real_claim],
            api_surface=[
                {"name": "OptionButtonControl", "doc": "Enables a single choice."},
            ],
        )
        claims = ci.load_claims("words", "net")
        assert real_claim in claims
        assert any(c["kind"] == "class_doc" for c in claims)
        assert len(claims) == 2

    def test_missing_claims_json_still_returns_class_doc_claims(self, tmp_path, monkeypatch):
        monkeypatch.setattr(ci, "KNOWLEDGE_ROOT", tmp_path)
        merged = tmp_path / "words" / "net" / "merged"
        merged.mkdir(parents=True)
        (merged / "api_surface.json").write_text(
            json.dumps([{"name": "Foo", "doc": "Foo does a thing."}]),
            encoding="utf-8",
        )
        claims = ci.load_claims("words", "net")
        assert len(claims) == 1
        assert claims[0]["kind"] == "class_doc"

    def test_neither_file_exists_returns_empty(self, tmp_path, monkeypatch):
        monkeypatch.setattr(ci, "KNOWLEDGE_ROOT", tmp_path)
        assert ci.load_claims("words", "net") == []


class TestBestTokenOverlapNoiseFloor:
    """MIN_OVERLAP_CLAIM_TOKENS: claims below the floor can't win the ratio
    tier on shared filler words alone (confirmed live: a 6-token words/net
    claim scored 0.43 overlap against an unrelated sentence)."""

    def test_short_claim_excluded_from_ratio_tier(self):
        line_tokens = ci.tokenize(
            "This interface provides 1 method for working with Foo objects in .NET programs."
        )
        # Real words/net claim (7 tokens) that scored 0.43 overlap against an
        # unrelated boilerplate sentence on shared filler words alone.
        short_claim_tokens = ci.tokenize("ResourceLoadingArgs: Provides data for the ResourceLoading method.")
        assert len(short_claim_tokens) < ci.MIN_OVERLAP_CLAIM_TOKENS
        overlap = ci.best_token_overlap(line_tokens, [short_claim_tokens])
        assert overlap == 0.0, "Claim below the floor must not contribute to the ratio tier"

    def test_pageset_all_property_claim_excluded_from_ratio_tier(self):
        """5-token mechanical claims (e.g. 'X.Y property of type Z') lose ratio-
        tier eligibility under the floor but remain reachable via TF-IDF, which
        is IDF-weighted and doesn't reward short claims unfairly."""
        claim_tokens = ci.tokenize("PageSet.All property of type PageSet")
        assert len(claim_tokens) < ci.MIN_OVERLAP_CLAIM_TOKENS

    def test_long_claim_still_eligible(self):
        line_tokens = ci.tokenize("This interface provides 1 method for working with Foo objects in .NET programs.")
        long_claim_tokens = ci.tokenize("Class Foo defined in Aspose.Words/Model/Fields/Foo.cs")
        assert len(long_claim_tokens) >= ci.MIN_OVERLAP_CLAIM_TOKENS
        overlap = ci.best_token_overlap(line_tokens, [long_claim_tokens])
        assert overlap > 0.0

    def test_empty_claim_list_returns_zero(self):
        assert ci.best_token_overlap(ci.tokenize("anything at all here"), []) == 0.0


class TestTfidfImportRestored:
    """Regression guard for the Wave-5-migration stale import: _claim_index.py
    used to `from embed import ...` (bare top-level import). embed.py was moved
    to commands/knowledge/embed.py in that migration and the import was never
    updated; the bare ImportError was silently caught, permanently stubbing
    TF-IDF to return 0.0 for prose_claim_binding, prose_truth, and
    prose_grounding -- all three evaluators had been running on the raw
    token-overlap ratio tier alone.
    """

    def test_tfidf_available(self):
        assert ci.TFIDF_AVAILABLE is True, (
            "TF-IDF must be importable from commands.knowledge.embed -- if "
            "this is False, the secondary semantic-matching tier is silently "
            "dead across every prose-grounding evaluator"
        )

    def test_tfidf_actually_computes_nonzero_similarity(self, tmp_path, monkeypatch):
        """A real functional check, not just an import check -- a stub that
        imports cleanly but still returns 0.0 would pass test_tfidf_available
        while remaining functionally broken."""
        monkeypatch.setattr(ci, "KNOWLEDGE_ROOT", tmp_path)
        _write_knowledge(tmp_path, claims=[
            {"claim_id": "C1", "text": "supports reading PDF documents with embedded fonts"},
        ])
        idx = ci.get_claim_index("words", "net")
        similarity = idx.best_similarity("This library supports reading PDF documents with embedded fonts")
        assert similarity > 0.5, (
            f"Expected high cosine similarity for near-identical text, got {similarity} "
            f"-- TF-IDF may still be stubbed"
        )


class TestInterfaceDocGroundingResolved:
    """Regression guard for the real words/net scenario: 6 Interface reference
    pages and OptionButtonControl.md failed prose_claim_binding because (a) the
    class/interface docstring was never captured as a claim, and (b) the TF-IDF
    tier that could have caught the class-name match via the existing
    "Class X defined in Y.cs" claim was silently dead (see
    TestTfidfImportRestored). Both fixes combined restore genuine, non-noisy
    grounding -- verified here via the real best_token_overlap + TF-IDF path,
    not a hand-rolled ratio calculation.
    """

    def test_interface_boilerplate_sentence_grounds_via_tfidf(self, tmp_path, monkeypatch):
        """Mirrors real data: claims.json already has a 'Class X defined in
        Y.cs' claim; TF-IDF's IDF-weighting on the rare class-name token is
        what legitimately grounds the boilerplate count sentence -- not the
        class_doc claim, and not raw token-overlap noise."""
        monkeypatch.setattr(ci, "KNOWLEDGE_ROOT", tmp_path)
        _write_knowledge(
            tmp_path,
            claims=[{
                "claim_id": "CLM-1",
                "kind": "api_class",
                "text": "Class IComparisonExpressionEvaluator defined in Aspose.Words/Model/Fields/IComparisonExpressionEvaluator.cs",
            }],
            api_surface=[{
                "name": "IComparisonExpressionEvaluator",
                "doc": (
                    "When implemented, allows to override default comparison "
                    "expressions evaluation for the FieldIf and FieldCompare fields."
                ),
            }],
        )
        line = (
            "This interface provides 1 method for working with "
            "IComparisonExpressionEvaluator objects in .NET programs."
        )
        idx = ci.get_claim_index("words", "net")
        similarity = idx.best_similarity(line)
        assert similarity >= 0.3, (
            f"Expected TF-IDF to ground the boilerplate sentence via the "
            f"shared class name, got {similarity}"
        )

    def test_real_class_docstring_prose_grounds_via_class_doc_claim(self, tmp_path, monkeypatch):
        """OptionButtonControl's Overview sentence IS the real docstring
        verbatim -- only the class_doc synthetic claim grounds it; no
        mechanical claim shares enough vocabulary."""
        monkeypatch.setattr(ci, "KNOWLEDGE_ROOT", tmp_path)
        _write_knowledge(
            tmp_path,
            claims=[
                {"claim_id": "CLM-1", "kind": "api_method",
                 "text": "OptionButtonControl.Selected property of type bool"},
                {"claim_id": "CLM-2", "kind": "api_class",
                 "text": "Class OptionButtonControl defined in Aspose.Words/RW/Ole/ActiveX/Forms2/OptionButtonControl.cs"},
            ],
            api_surface=[{
                "name": "OptionButtonControl",
                "doc": (
                    "The OptionButton control enables a single choice in a "
                    "limited set of mutually exclusive choices."
                ),
            }],
        )
        line = (
            "The OptionButton control enables a single choice in a limited "
            "set of mutually exclusive choices."
        )
        claims = ci.load_claims("words", "net")
        claim_token_sets = [ci.tokenize(c["text"]) for c in claims]
        overlap = ci.best_token_overlap(ci.tokenize(line), claim_token_sets)
        idx = ci.get_claim_index("words", "net")
        similarity = idx.best_similarity(line)
        assert overlap >= 0.3 or similarity >= 0.3, (
            f"Expected class_doc claim to ground the real docstring sentence "
            f"(overlap={overlap}, similarity={similarity})"
        )
        # And it should be the class_doc claim doing the work, not a mechanical one
        mechanical_only_token_sets = [
            ci.tokenize(c["text"]) for c in claims if c.get("kind") != "class_doc"
        ]
        mechanical_overlap = ci.best_token_overlap(ci.tokenize(line), mechanical_only_token_sets)
        assert mechanical_overlap < 0.3, (
            "Mechanical signature claims alone should NOT ground this descriptive "
            "sentence -- if they do, the test fixture no longer isolates the fix"
        )

    def test_fabricated_capability_still_ungrounded(self, tmp_path, monkeypatch):
        """The fix must not weaken grounding for genuinely fabricated claims --
        a class_doc claim only matches its own real docstring text, not
        unrelated invented prose."""
        monkeypatch.setattr(ci, "KNOWLEDGE_ROOT", tmp_path)
        _write_knowledge(tmp_path, api_surface=[
            {"name": "OptionButtonControl", "doc": "Enables a single choice."},
        ])
        line = "This library supports quantum teleportation of spreadsheet data across galaxies."
        claims = ci.load_claims("words", "net")
        claim_token_sets = [ci.tokenize(c["text"]) for c in claims]
        overlap = ci.best_token_overlap(ci.tokenize(line), claim_token_sets)
        idx = ci.get_claim_index("words", "net")
        similarity = idx.best_similarity(line)
        assert overlap < 0.3
        assert similarity < 0.3


class TestIsMarkdownTableRow:
    """Root cause: Properties/Methods table rows on reference pages are always
    generated verbatim from api_surface.json's per-member `doc` field (see
    batch_reference.py), and are already verified by dedicated table-focused
    evaluators (member_validity.py, api_accuracy.py). Scanning their cell text
    as free-standing prose produced false positives once real TF-IDF and the
    tightened overlap floor stopped rubber-stamping everything: real docs like
    "Deletes all tab stop positions." or "Returns true if the LineStyle is not
    None." tripped prose_truth's strong-wording check and prose_claim_binding's
    grounding check on ordinary technical description, not marketing prose.
    """

    @pytest.mark.parametrize("line", [
        "| `IsVisible` | `bool` | Read | Returns true if the LineStyle is not None. |",
        "| `Clear()` | Deletes all tab stop positions. |",
        "| `HyphenateCaps` | `bool` | Read/Write | Gets or sets value determining whether words written in all capital letters are hyphenated. |",
        "|`A`|`B`|",
    ])
    def test_table_row_detected(self, line):
        assert ci.is_markdown_table_row(line)

    @pytest.mark.parametrize("line", [
        "This class provides 12 methods for working with FieldSeparator objects in .NET programs.",
        "The OptionButton control enables a single choice in a limited set of mutually exclusive choices.",
        "Use the `Document` class to load a file that contains a pipe | character in prose.",
    ])
    def test_ordinary_prose_not_detected(self, line):
        assert not ci.is_markdown_table_row(line)


class TestIsIdentifierEnumeration:
    """Root cause: batch_reference.py's LC-10 fix generates 'Available methods
    include: `A`, `B`, ...' and 'Properties: `A`, `B`, ...' sentences entirely
    from api_surface.json's own name lists (its own comment: "Only
    method/property/member names from api_surface.json are used -- no
    hallucinated claims"). claims.json has no reason to contain a claim that
    just restates a name list, so prose_claim_binding could never find a match
    for a correctly-generated page -- confirmed live across 48 of 707 words/net
    reference pages once ratio-tier noise stopped accidentally covering for it.
    """

    def test_available_methods_sentence_detected(self):
        line = (
            "Available methods include: `Add`, `Clear`, `Contains`, `GetByName`, "
            "`GetEnumerator`, `IndexOfKey`, `Remove`, `RemoveAt`."
        )
        assert ci.is_identifier_enumeration(line)

    def test_available_methods_with_trailing_count_detected(self):
        line = (
            "Available methods include: `Accept`, `AcceptEnd`, `AcceptStart`, "
            "`AppendChild`, `Cell`, `Clone`, and 17 additional methods."
        )
        assert ci.is_identifier_enumeration(line)

    def test_properties_enumeration_detected(self):
        line = "Properties: `CustomNodeId`, `Document`, `FieldType`, and 12 more."
        assert ci.is_identifier_enumeration(line)

    def test_two_identifiers_not_enumeration(self):
        """Below _MIN_ENUMERATION_IDENTIFIERS -- an ordinary sentence
        referencing one or two identifiers, not a structural listing."""
        line = "The `Document` class provides access to `DocumentBuilder` for editing."
        assert not ci.is_identifier_enumeration(line)

    def test_many_identifiers_with_substantial_prose_not_enumeration(self):
        """Even with several backticked identifiers, real surrounding prose
        (an actual assertion, not just list-introduction glue) must still be
        checked -- this guards against the recognizer being too permissive."""
        line = (
            "Developers report that `Foo`, `Bar`, and `Baz` together deliver "
            "dramatically faster performance than any competing library on "
            "the market today according to internal benchmarks."
        )
        assert not ci.is_identifier_enumeration(line)

    def test_table_row_with_backticks_not_misclassified_as_enumeration(self):
        """A table row with only 2 backtick cells and real descriptive prose
        must go through is_markdown_table_row, not this recognizer."""
        line = "| `IncludeFullPath` | `bool` | Read/Write | Gets or sets whether to include the full file path name. |"
        assert not ci.is_identifier_enumeration(line)

    def test_short_trailing_claim_not_misclassified_as_enumeration(self):
        """Found via independent review: a short trailing assertion ('fully
        support advanced editing') stays within the residual-word budget, so
        word-count alone would misclassify this as a pure list. The list is
        the SUBJECT of a claim here, not introduced by connective glue -- the
        trailing claim-verb check must catch what the word-count check alone
        cannot."""
        line = "`A`, `B`, `C` fully support advanced editing."
        assert not ci.is_identifier_enumeration(line)

    @pytest.mark.parametrize("line", [
        "`X`, `Y`, `Z` together deliver best-in-class performance.",
        "`X`, `Y`, `Z` provide everything you need.",
    ])
    def test_other_short_trailing_claims_not_misclassified(self, line):
        assert not ci.is_identifier_enumeration(line)
