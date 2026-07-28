"""C++ snippet extraction: gtest macros, and the hand-rolled smoke-test main()
idiom (pdf/cpp launch hardening, MT012).

Confirmed live against pdf/cpp's real source
(runs/.clone_cache/aspose_pdf_cpp/tests/): 134/155 test files use real gtest
TEST()/TEST_F() macros (already recognized). The remaining 21 use a
repo-specific idiom instead — a bare `int main()` with a local `Check(bool,
name)` pass/fail helper, e.g. document_info_test.cpp — living in a "tests"
dir, not an "examples" dir, so the pre-existing `is_example_dir and fname ==
"main"` condition never fired for them. This suite covers both the
already-working gtest path (regression guard) and the new filename-based
smoke-test main() recognition.

Also confirmed live: cells/cpp's snippet_count=2 (vs. pdf/cpp's 100, capped)
was NOT caused by a missing cpp-specific pattern — its real gtest suite lives
under a compound-named top-level dir (`Aspose.Cells.Foss.Cpp.Tests`), and the
generic directory token-matching fix already landed 2026-07-22 (commit
7d3d8cd27e, scripts/pipeline/tests/extraction/test_snippet_dir_matching.py)
already finds it correctly when re-scouted — cells/cpp's knowledge/ was last
promoted 2026-07-12, predating that fix. No new cpp-specific directory-finding
work was needed; this is a pre-existing, generically-tested mechanism, not a
gap this mission re-solves.
"""
from __future__ import annotations

from extraction.snippets import _collect_snippet_functions
from extraction.tree_helpers import _CLASS_TYPES, _FUNC_TYPES, get_parser

_GTEST_SOURCE = """
#include <gtest/gtest.h>

TEST(ActionsSmoke, NamedActionFromPredefined) {
    EXPECT_EQ(1, 1);
}
"""

_SMOKE_MAIN_SOURCE = """
#include <iostream>

namespace {
int passed = 0, failed = 0;
void Check(bool c, const char* n) {
    if (c) { ++passed; } else { ++failed; }
}
}

int main() {
    Check(true, "sample");
    return failed == 0 ? 0 : 1;
}
"""

_PLAIN_HELPER_SOURCE = """
int Add(int a, int b) {
    return a + b;
}
"""


def _parse(source: str):
    parser = get_parser("cpp")
    return parser.parse(source.encode("utf-8")).root_node


def _collect(source: str, *, is_example_dir: bool = False, file_stem: str = ""):
    root = _parse(source)
    return _collect_snippet_functions(
        root, "cpp", _FUNC_TYPES["cpp"], _CLASS_TYPES.get("cpp", set()),
        source, is_example_dir=is_example_dir, file_stem=file_stem)


def test_gtest_macro_recognized_regardless_of_filename():
    results = _collect(_GTEST_SOURCE, file_stem="actions_smoke_test")
    names = {r[0] for r in results}
    assert "TEST" in names


def test_bare_main_in_tests_dir_not_recognized_without_test_suffix():
    """Regression guard: a plain main() in a non-example, non-test-suffixed
    file must NOT be swept up as a snippet (e.g. a build helper/driver)."""
    results = _collect(_SMOKE_MAIN_SOURCE, is_example_dir=False, file_stem="helper")
    assert results == []


def test_smoke_test_suffixed_main_is_recognized():
    results = _collect(_SMOKE_MAIN_SOURCE, is_example_dir=False,
                        file_stem="document_info_test")
    names = {r[0] for r in results}
    assert "main" in names


def test_smoke_test_double_suffix_is_recognized():
    results = _collect(_SMOKE_MAIN_SOURCE, is_example_dir=False,
                        file_stem="actions_smoke_test")
    names = {r[0] for r in results}
    assert "main" in names


def test_example_dir_main_recognition_unaffected():
    """Regression guard: the pre-existing is_example_dir path is unchanged."""
    results = _collect(_SMOKE_MAIN_SOURCE, is_example_dir=True, file_stem="01_pages")
    names = {r[0] for r in results}
    assert "main" in names


def test_plain_helper_function_not_recognized():
    results = _collect(_PLAIN_HELPER_SOURCE, is_example_dir=False,
                        file_stem="math_utils_test")
    assert results == []
