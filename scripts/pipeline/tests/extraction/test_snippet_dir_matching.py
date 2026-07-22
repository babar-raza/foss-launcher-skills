"""HARDEN-words-net: snippet extraction must find C#-solution-style compound
test directory names, not just literal "tests"/"examples"/etc.

words/net's actual test directory is named `Aspose.Words.Tests` (a standard
.NET solution naming convention: `{Product}.Tests`). The pre-existing
`snippet_dirs` matching in extraction/snippets.py did an EXACT child-directory
join (`repo / "tests"`), which never matches a compound name like this —
words/net's scout run found only 1 code snippet as a result (vs. 100, the
cap, for sibling .NET products whose repos happen to have a literal `tests/`
directory). Verified pre-existing elsewhere too: `cells/net` shows the same
shape (2 snippets) for the same reason.
"""
from __future__ import annotations

from extraction.snippets import _dir_name_matches_pattern, _is_product_affine, extract_snippets
from extraction.tree_helpers import _CLASS_TYPES, _FUNC_TYPES, get_parser


class TestDirNameMatchesPattern:
    def test_exact_match_case_insensitive(self):
        assert _dir_name_matches_pattern("tests", "tests") is True
        assert _dir_name_matches_pattern("Tests", "tests") is True
        assert _dir_name_matches_pattern("ApiExamples", "ApiExamples") is True

    def test_compound_dotnet_solution_name_matches_as_token(self):
        assert _dir_name_matches_pattern("Aspose.Words.Tests", "tests") is True
        assert _dir_name_matches_pattern("Aspose.Words.Tests", "test") is False  # "test" != "tests" token
        assert _dir_name_matches_pattern("My-Product.Examples", "examples") is True
        assert _dir_name_matches_pattern("my_product_test", "test") is True

    def test_substring_false_positives_avoided(self):
        """Names that merely CONTAIN the pattern as a substring (not a whole
        token) must not match -- this is the precision guard against a much
        noisier fix."""
        assert _dir_name_matches_pattern("Latest", "test") is False
        assert _dir_name_matches_pattern("Contest", "test") is False
        assert _dir_name_matches_pattern("Testament", "test") is False

    def test_test_framework_helper_dir_not_matched(self):
        """Aspose.Words.TestFx is a test-framework helper library, not an
        example/test-content directory -- tokenizes to 'testfx', not 'test',
        correctly excluded (it holds no example code worth extracting)."""
        assert _dir_name_matches_pattern("Aspose.Words.TestFx", "test") is False
        assert _dir_name_matches_pattern("Aspose.Words.TestFx", "tests") is False


class TestExtractSnippetsCompoundDirNames:
    """End-to-end: extract_snippets must find real snippets in a
    Aspose.Words.Tests-shaped fixture, which it could not before this fix."""

    def _write_test_class(self, path):
        path.write_text(
            "using System;\n"
            "namespace Aspose.Words.Tests {\n"
            "    public class DocumentTests {\n"
            "        public void TestOpenDocument() {\n"
            "            var doc = new Document();\n"
            "        }\n"
            "    }\n"
            "}\n",
            encoding="utf-8",
        )

    def test_compound_test_dir_name_yields_snippets(self, tmp_path):
        pkg_root = tmp_path / "Aspose.Words"
        pkg_root.mkdir()
        test_dir = tmp_path / "Aspose.Words.Tests"
        test_dir.mkdir()
        self._write_test_class(test_dir / "DocumentTests.cs")

        parser = get_parser("csharp")
        snippets = extract_snippets(
            parser, "csharp", pkg_root, tmp_path,
            classes=[], formats=[],
        )

        assert len(snippets) >= 1, (
            "expected at least one snippet from Aspose.Words.Tests/ -- this "
            "is exactly the shape that produced 0-1 snippets before the fix"
        )
        assert any(s["source_function"] == "TestOpenDocument" for s in snippets)

    def test_unrelated_similarly_named_dir_not_scanned(self, tmp_path):
        """A directory that merely contains 'test' as a substring (not a
        whole token) must not be treated as a snippet source -- guards
        against the fix being too permissive."""
        pkg_root = tmp_path / "Aspose.Words"
        pkg_root.mkdir()
        latest_dir = tmp_path / "Latest"
        latest_dir.mkdir()
        self._write_test_class(latest_dir / "DocumentTests.cs")

        parser = get_parser("csharp")
        snippets = extract_snippets(
            parser, "csharp", pkg_root, tmp_path,
            classes=[], formats=[],
        )

        assert snippets == []


class TestIsProductAffine:
    def test_exact_and_dot_prefix_match(self):
        assert _is_product_affine("Aspose.Words", "Aspose.Words") is True
        assert _is_product_affine("Aspose.Words.Tests", "Aspose.Words") is True

    def test_unrelated_sibling_not_affine(self):
        """Aspose.JavaMs.Tests is a bundled dependency's OWN test suite —
        does not share the "Aspose.Words" namespace prefix, must not be
        considered affine."""
        assert _is_product_affine("Aspose.JavaMs.Tests", "Aspose.Words") is False

    def test_prefix_must_be_delimited_not_just_startswith(self):
        """A name that merely STARTS WITH the package name as a raw string
        (no delimiter) must not count -- e.g. "Aspose.WordsExtra.Tests" is a
        different product, not "Aspose.Words" + a suffix."""
        assert _is_product_affine("Aspose.WordsExtra.Tests", "Aspose.Words") is False


class TestCompetingSiblingDirectories:
    """The exact real-world shape found live on words/net: MULTIPLE
    directories token-match "tests" under the same search base, one
    belonging to the product (Aspose.Words.Tests) and one belonging to an
    unrelated bundled dependency (Aspose.JavaMs.Tests) that happens to sort
    first alphabetically. Before the product-affinity fix, the unrelated
    directory silently exhausted the entire snippet budget first."""

    def _write_class(self, path, namespace, class_name, method_name, body):
        path.write_text(
            f"using System;\n"
            f"namespace {namespace} {{\n"
            f"    public class {class_name} {{\n"
            f"        public void {method_name}() {{\n"
            f"            {body}\n"
            f"        }}\n"
            f"    }}\n"
            f"}}\n",
            encoding="utf-8",
        )

    def test_product_affine_sibling_wins_over_unrelated_dependency(self, tmp_path, monkeypatch):
        import extraction.snippets as snippets_mod

        # Cap the snippet budget tightly so an unfixed version would visibly
        # exhaust it entirely on the wrong (alphabetically-first) directory.
        monkeypatch.setattr(snippets_mod, "MAX_SNIPPETS", 1)

        pkg_root = tmp_path / "Aspose.Words"
        pkg_root.mkdir()

        # Sorts BEFORE Aspose.Words.Tests alphabetically -- reproduces the
        # exact ordering that caused the real bug.
        unrelated_dir = tmp_path / "Aspose.JavaMs.Tests"
        unrelated_dir.mkdir()
        self._write_class(unrelated_dir / "BigIntegerTests.cs",
                          "Aspose.JavaMs.Tests", "BigIntegerTests",
                          "TestToUnsignedArray", "var x = 1;")

        real_dir = tmp_path / "Aspose.Words.Tests"
        real_dir.mkdir()
        self._write_class(real_dir / "DocumentTests.cs",
                          "Aspose.Words.Tests", "DocumentTests",
                          "TestOpenDocument", "var doc = new Document();")

        parser = get_parser("csharp")
        snippets = extract_snippets(
            parser, "csharp", pkg_root, tmp_path,
            classes=[], formats=[],
        )

        assert len(snippets) == 1
        assert snippets[0]["source_function"] == "TestOpenDocument", (
            "the product's OWN test (Aspose.Words.Tests) must win over an "
            "unrelated bundled dependency's test suite (Aspose.JavaMs.Tests), "
            "even though the latter sorts first alphabetically -- this is "
            "the exact real-world failure mode found on words/net"
        )

    def test_no_affine_match_falls_back_to_all_with_warning(self, tmp_path, monkeypatch, caplog):
        """If NEITHER sibling shares the package's namespace prefix, fall
        back to including all token matches (better degraded coverage than
        none) but log a warning so the ambiguity is visible, not silent."""
        import logging
        import extraction.snippets as snippets_mod

        monkeypatch.setattr(snippets_mod, "MAX_SNIPPETS", 100)

        pkg_root = tmp_path / "SomeProduct"
        pkg_root.mkdir()

        dir_a = tmp_path / "VendorA.Tests"
        dir_a.mkdir()
        self._write_class(dir_a / "AT.cs", "VendorA.Tests", "ATTests", "TestA", "var x = 1;")

        dir_b = tmp_path / "VendorB.Tests"
        dir_b.mkdir()
        self._write_class(dir_b / "BT.cs", "VendorB.Tests", "BTTests", "TestB", "var x = 1;")

        parser = get_parser("csharp")
        with caplog.at_level(logging.WARNING, logger="extraction.snippets"):
            snippets = extract_snippets(
                parser, "csharp", pkg_root, tmp_path,
                classes=[], formats=[],
            )

        fn_names = {s["source_function"] for s in snippets}
        assert fn_names == {"TestA", "TestB"}, "with no affine candidate, both unrelated dirs are used (degraded, not empty)"
        assert any("token-match" in r.message for r in caplog.records), (
            "an ambiguous multi-directory match with no product affinity "
            "must be logged, not silently resolved"
        )
