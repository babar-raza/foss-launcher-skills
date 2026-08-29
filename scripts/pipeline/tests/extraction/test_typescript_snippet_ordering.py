"""TC-MT040-44 (D-5) + TC-MT040-16 (G-TS-04): deterministic tiered snippet
budget and TypeScript snippet-source hygiene.

Covers extraction/snippets.py:
  - _extract_snippets_tiered / the tier-dispatch in extract_snippets
    (README fences tier 0 <=10, curated examples/samples tier 1 <=60,
    tests tier 2 remainder up to MAX_SNIPPETS -- opted in for
    typescript/javascript ONLY via _TIERED_SNIPPET_PLATFORMS)
  - _leaf_test_blocks (drop a describe() wrapper that strictly contains
    already-collected it()/test() blocks)
  - the TS/JS test-dir file-hygiene gate in _collect_snippet_functions
    (a file under test/tests not itself named like a test file
    contributes nothing, e.g. test/helpers/util.ts)
  - _compute_snippet_key / _normalize_snippet_code (additive identity,
    TS/JS tiered path only)
  - determinism: _collect_tier_candidates sorts its input explicitly, so
    a shuffled `files` list still produces identical output -- this is
    the seam that proves determinism without faking os.listdir ordering.

Byte-parity requirement: a NON-opted-in platform (python) must produce
IDENTICAL output before and after this change. tests/fixtures/
extraction_goldens/snippet_golden_pkg_python_snippets.json was captured by
dynamically loading the git-HEAD (pre-change) extraction/snippets.py and
running it against tests/fixtures/snippet_golden_pkg/, then confirmed
byte-identical to the post-change module's output on the same fixture
before being committed as the golden (see git history / mission report for
the one-shot comparison script's output).
"""
from __future__ import annotations

import json
import re
import shutil
from pathlib import Path

# sys.path is set by tests/conftest.py -- no manual insert needed here.
from extraction.snippets import (
    MAX_SNIPPETS,
    _DEFAULT_SNIPPET_DIRS,
    _TIER2_TEST_DIR_NAMES,
    _TIERED_SNIPPET_PLATFORMS,
    _TS_TEST_FILE_RE,
    _collect_snippet_functions,
    _collect_tier_candidates,
    _compute_snippet_key,
    _discover_snippet_dir_files,
    _leaf_test_blocks,
    _normalize_snippet_code,
    _search_base_list,
    extract_snippets,
)
from extraction.tree_helpers import _CLASS_TYPES, _FUNC_TYPES, get_parser

FIXTURES = Path(__file__).resolve().parents[1] / "fixtures"
TS_FIXTURE = FIXTURES / "ts_flat_package"
GOLDEN_PKG = FIXTURES / "snippet_golden_pkg"
GOLDEN_JSON = FIXTURES / "extraction_goldens" / "snippet_golden_pkg_python_snippets.json"


def _copy_ts_fixture(dest: Path) -> Path:
    shutil.copytree(TS_FIXTURE, dest, dirs_exist_ok=True)
    return dest


def _generate_bulk_fixture(dest: Path, n_test_files: int = 30, its_per_file: int = 4) -> Path:
    """Copy ts_flat_package into *dest* and add N generated
    test/gen_{i}.test.ts files, each a describe() holding `its_per_file`
    leaf it() blocks -- mirrors the design doc's own recipe for proving the
    tiered budget at scale (30 files * 4 its = 120 leaf blocks, comfortably
    over MAX_SNIPPETS)."""
    fixture = _copy_ts_fixture(dest)
    test_dir = fixture / "test"
    for i in range(n_test_files):
        its = "\n".join(
            f"  it('case {i}-{j}', () => {{ const x = {j}; }});"
            for j in range(its_per_file)
        )
        (test_dir / f"gen_{i}.test.ts").write_text(
            f"describe('Generated {i}', () => {{\n{its}\n}});\n",
            encoding="utf-8",
        )
    return fixture


# ---------------------------------------------------------------------------
# Legacy path untouched (dispatch scoping)
# ---------------------------------------------------------------------------

class TestDispatchScoping:
    def test_only_typescript_and_javascript_are_tiered(self):
        assert _TIERED_SNIPPET_PLATFORMS == {"typescript", "javascript"}

    def test_default_snippet_dirs_literal_pinned(self):
        """Regression pin: the legacy iteration-order list is untouched --
        still puts tests/test before examples/*, exactly as before."""
        assert _DEFAULT_SNIPPET_DIRS == [
            "tests", "test", "examples", "example", "samples",
            "demo", "ApiExamples", "api_examples", "_examples",
        ]


class TestNonOptedInPlatformGoldenParity:
    """The hard requirement: python (not in _TIERED_SNIPPET_PLATFORMS) must
    produce byte-identical extract_snippets() output before and after
    TC-MT040-44/16."""

    def test_python_snippet_output_byte_identical_to_pre_change_golden(self):
        with open(GOLDEN_JSON, encoding="utf-8") as f:
            golden = json.load(f)
        parser = get_parser("python")
        current = extract_snippets(
            parser, "python", GOLDEN_PKG, GOLDEN_PKG, classes=[], formats=[])
        assert current == golden

    def test_python_snippet_output_has_no_snippet_key_field(self):
        """snippet_key is additive ONLY for the tiered (TS/JS) path -- a
        non-opted-in platform must never gain a new field, which is what
        makes byte-identical golden comparison meaningful in the first
        place."""
        parser = get_parser("python")
        current = extract_snippets(
            parser, "python", GOLDEN_PKG, GOLDEN_PKG, classes=[], formats=[])
        assert current, "fixture must actually produce snippets for this to be a meaningful check"
        assert all("snippet_key" not in s for s in current)

    def test_python_snippet_dir_order_is_tests_before_examples(self):
        """Confirms the legacy tests-before-examples starvation behavior is
        UNCHANGED for python -- this card intentionally does not fix it for
        non-opted-in platforms."""
        parser = get_parser("python")
        current = extract_snippets(
            parser, "python", GOLDEN_PKG, GOLDEN_PKG, classes=[], formats=[])
        first_non_readme = next(
            s for s in current if s["source_function"] != "(readme_block)")
        assert first_non_readme["source_file"].startswith("tests/")


# ---------------------------------------------------------------------------
# TC-MT040-16 (G-TS-04a): leaf-only test blocks
# ---------------------------------------------------------------------------

class TestLeafTestBlocksPure:
    """Unit tests directly against _leaf_test_blocks / _collect_snippet_functions,
    independent of the tiered budget or fixture files."""

    def test_wrapper_dropped_leaves_kept(self):
        parser = get_parser("typescript")
        src = (
            "describe('outer', () => {\n"
            "  it('a', () => {});\n"
            "  it('b', () => {});\n"
            "});\n"
        ).encode("utf-8")
        root = parser.parse(src).root_node
        text = src.decode("utf-8")
        results = _collect_snippet_functions(
            root, "typescript", _FUNC_TYPES["typescript"],
            _CLASS_TYPES.get("typescript", set()), text,
            is_example_dir=False, file_stem="x.test")
        names = {r[0] for r in results}
        assert names == {"a", "b"}
        assert "outer" not in names

    def test_triple_nested_describe_keeps_only_innermost_leaves(self):
        parser = get_parser("typescript")
        src = (
            "describe('outer', () => {\n"
            "  describe('inner', () => {\n"
            "    it('leaf', () => {});\n"
            "  });\n"
            "});\n"
        ).encode("utf-8")
        root = parser.parse(src).root_node
        text = src.decode("utf-8")
        results = _collect_snippet_functions(
            root, "typescript", _FUNC_TYPES["typescript"],
            _CLASS_TYPES.get("typescript", set()), text,
            is_example_dir=False, file_stem="x.test")
        names = {r[0] for r in results}
        assert names == {"leaf"}

    def test_describe_with_no_nested_blocks_kept_as_its_own_leaf(self):
        parser = get_parser("typescript")
        src = b"describe('lonely', () => {\n  const x = 1;\n});\n"
        root = parser.parse(src).root_node
        text = src.decode("utf-8")
        results = _collect_snippet_functions(
            root, "typescript", _FUNC_TYPES["typescript"],
            _CLASS_TYPES.get("typescript", set()), text,
            is_example_dir=False, file_stem="x.test")
        names = {r[0] for r in results}
        assert names == {"lonely"}

    def test_leaf_test_blocks_is_order_independent(self):
        """Pure function contract: the SAME set of blocks in a different
        input order yields the same leaf set."""
        parser = get_parser("typescript")
        src = (
            "describe('outer', () => {\n"
            "  it('a', () => {});\n"
            "  it('b', () => {});\n"
            "  it('c', () => {});\n"
            "});\n"
        ).encode("utf-8")
        root = parser.parse(src).root_node

        from extraction.tree_helpers import child_by_field, collect_nodes, node_text
        blocks = []
        for call_node in collect_nodes(root, {"call_expression"}):
            fn_part = child_by_field(call_node, "function")
            if fn_part and node_text(fn_part) in {"test", "it", "describe"}:
                args = child_by_field(call_node, "arguments")
                desc = ""
                for ch in args.children:
                    if ch.type in ("string", "template_string"):
                        desc = node_text(ch).strip("'\"` ")
                        break
                blocks.append((desc, call_node, call_node.start_point[0] + 1))

        forward = {n for n, _, _ in _leaf_test_blocks(blocks)}
        reversed_blocks = list(reversed(blocks))
        backward = {n for n, _, _ in _leaf_test_blocks(reversed_blocks)}
        assert forward == backward == {"a", "b", "c"}

    def test_end_to_end_document_test_ts_drops_describe_keeps_three_its(self):
        """End-to-end against the checked-in fixture file, not a synthetic
        string -- ties the unit-level behavior to the real fixture used by
        the tiered-budget tests below."""
        parser = get_parser("typescript")
        src = (TS_FIXTURE / "test" / "document.test.ts").read_bytes()
        root = parser.parse(src).root_node
        text = src.decode("utf-8")
        results = _collect_snippet_functions(
            root, "typescript", _FUNC_TYPES["typescript"],
            _CLASS_TYPES.get("typescript", set()), text,
            is_example_dir=False, file_stem="document.test")
        names = {r[0] for r in results}
        assert names == {"opens a document", "saves a document", "round-trips open then save"}
        assert "Document" not in names  # the describe('Document', ...) wrapper title


class TestLeafOnlyEndToEnd:
    """Same assertion, but through the real extract_snippets() entry point
    against the ts_flat_package fixture (proves the tiered path wires the
    leaf filter through correctly, not just the unit-level helper)."""

    def test_describe_wrapper_never_appears_as_its_own_snippet(self, tmp_path):
        fixture = _copy_ts_fixture(tmp_path / "pkg")
        parser = get_parser("typescript")
        snippets = extract_snippets(
            parser, "typescript", fixture / "src", fixture, classes=[], formats=[])
        doc_test_snippets = [s for s in snippets if s["source_file"] == "test/document.test.ts"]
        names = {s["source_function"] for s in doc_test_snippets}
        assert names == {"opens a document", "saves a document", "round-trips open then save"}
        assert "Document" not in names


# ---------------------------------------------------------------------------
# TC-MT040-16 (G-TS-04b): test-dir file hygiene
# ---------------------------------------------------------------------------

class TestTestDirFileHygienePure:
    def test_ts_test_file_re_matches_expected_shapes(self):
        for stem in ("document.test", "document.spec", "test_document", "document_test"):
            assert _TS_TEST_FILE_RE.search(stem), stem

    def test_ts_test_file_re_rejects_plain_names(self):
        for stem in ("util", "helpers", "forms", "index"):
            assert not _TS_TEST_FILE_RE.search(stem), stem

    def test_non_test_named_file_in_test_dir_returns_nothing(self):
        parser = get_parser("typescript")
        src = b"export function helper() { return 1; }\n"
        root = parser.parse(src).root_node
        text = src.decode("utf-8")
        results = _collect_snippet_functions(
            root, "typescript", _FUNC_TYPES["typescript"],
            _CLASS_TYPES.get("typescript", set()), text,
            is_example_dir=False, file_stem="util")
        assert results == []

    def test_test_suffixed_file_still_collected(self):
        parser = get_parser("typescript")
        src = b"export function helper() { return 1; }\n"
        root = parser.parse(src).root_node
        text = src.decode("utf-8")
        results = _collect_snippet_functions(
            root, "typescript", _FUNC_TYPES["typescript"],
            _CLASS_TYPES.get("typescript", set()), text,
            is_example_dir=False, file_stem="helper.test")
        names = {r[0] for r in results}
        assert "helper" in names

    def test_example_dir_files_never_gated_by_test_naming(self):
        """is_example_dir=True bypasses the hygiene gate entirely -- an
        example file is never required to look like a test file."""
        parser = get_parser("typescript")
        src = b"export function addForm() { return 1; }\n"
        root = parser.parse(src).root_node
        text = src.decode("utf-8")
        results = _collect_snippet_functions(
            root, "typescript", _FUNC_TYPES["typescript"],
            _CLASS_TYPES.get("typescript", set()), text,
            is_example_dir=True, file_stem="forms")
        names = {r[0] for r in results}
        assert "addForm" in names


class TestTestHelpersFileEndToEnd:
    def test_test_helpers_file_contributes_zero_snippets(self, tmp_path):
        fixture = _copy_ts_fixture(tmp_path / "pkg")
        parser = get_parser("typescript")
        snippets = extract_snippets(
            parser, "typescript", fixture / "src", fixture, classes=[], formats=[])
        assert not any(s["source_file"].startswith("test/helpers/") for s in snippets)
        assert not any(s["source_function"] == "makeDoc" for s in snippets)


# ---------------------------------------------------------------------------
# Negative control: docs/**/*.md fences never harvested
# ---------------------------------------------------------------------------

class TestDocsNegativeControl:
    def test_docs_markdown_fences_never_harvested(self, tmp_path):
        fixture = _copy_ts_fixture(tmp_path / "pkg")
        assert (fixture / "docs" / "superpowers" / "plans" / "plan.md").exists(), (
            "fixture setup sanity: the docs/ planning file must exist for "
            "this negative control to mean anything"
        )
        parser = get_parser("typescript")
        snippets = extract_snippets(
            parser, "typescript", fixture / "src", fixture, classes=[], formats=[])
        assert not any("docs/" in s["source_file"] for s in snippets)
        assert not any(s["source_function"] == "shouldNeverBeHarvested" for s in snippets)


# ---------------------------------------------------------------------------
# TC-MT040-44 (D-5): tiered budget
# ---------------------------------------------------------------------------

class TestTieredBudget:
    def test_examples_survive_tests_fill_remainder(self, tmp_path):
        """The exact live defect this card fixes: with 1 curated example
        function and far more than MAX_SNIPPETS worth of test leaf blocks,
        the example must survive (tier 1) and tests fill the remainder
        (tier 2) -- unlike the legacy iteration-order path, which would put
        tests first and could starve examples out entirely."""
        fixture = _generate_bulk_fixture(tmp_path)
        parser = get_parser("typescript")
        snippets = extract_snippets(
            parser, "typescript", fixture / "src", fixture, classes=[], formats=[])

        assert len(snippets) == MAX_SNIPPETS

        example_snippets = [s for s in snippets if s["source_file"].startswith("examples/")]
        assert any(s["source_function"] == "addForm" for s in example_snippets)

        test_snippets = [s for s in snippets if s["source_file"].startswith("test/")]
        assert len(test_snippets) > 0

    def test_snippet_ids_are_tier_ordered_readme_then_examples_then_tests(self, tmp_path):
        fixture = _generate_bulk_fixture(tmp_path)
        parser = get_parser("typescript")
        snippets = extract_snippets(
            parser, "typescript", fixture / "src", fixture, classes=[], formats=[])

        def _tier(s):
            if s["source_function"] == "(readme_block)":
                return 0
            if s["source_file"].startswith("examples/"):
                return 1
            return 2

        tiers = [_tier(s) for s in snippets]
        assert tiers == sorted(tiers)
        # snippet_NNN ids must match array position (positional ids, as before)
        assert [s["id"] for s in snippets] == [f"snippet_{i:03d}" for i in range(1, len(snippets) + 1)]

    def test_no_examples_dir_degrades_gracefully_to_tests_only(self, tmp_path):
        """3d/typescript's real live shape: no examples/ directory at all.
        Must not error -- degrades to README (if any) + tests, same total
        cap."""
        fixture = _copy_ts_fixture(tmp_path / "pkg")
        shutil.rmtree(fixture / "examples")
        parser = get_parser("typescript")
        snippets = extract_snippets(
            parser, "typescript", fixture / "src", fixture, classes=[], formats=[])
        assert not any(s["source_file"].startswith("examples/") for s in snippets)
        assert len(snippets) >= 1  # README + the 3 leaf it() blocks survive

    def test_tier_budgets_are_capped_individually(self, tmp_path):
        """Tier 0 <= 10, tier 1 <= 60 even when more candidates exist."""
        fixture = _copy_ts_fixture(tmp_path / "pkg")
        examples_dir = fixture / "examples" / "feature-showcase"
        for i in range(70):
            (examples_dir / f"gen_example_{i}.ts").write_text(
                f"export function genExample{i}(): void {{}}\n", encoding="utf-8")
        parser = get_parser("typescript")
        snippets = extract_snippets(
            parser, "typescript", fixture / "src", fixture, classes=[], formats=[])
        example_snippets = [s for s in snippets if s["source_file"].startswith("examples/")]
        assert len(example_snippets) == 60


# ---------------------------------------------------------------------------
# Determinism (the seam: explicit sort, not filesystem iteration order)
# ---------------------------------------------------------------------------

class TestDeterminismSeam:
    def test_collect_tier_candidates_is_independent_of_input_list_order(self, tmp_path):
        """The determinism seam TC-MT040-44 requires: _collect_tier_candidates
        sorts its input explicitly by (path, line, function), so passing its
        `files` argument in a SHUFFLED order -- rather than needing to fake
        os.listdir/Path.rglob's own iteration order -- still yields an
        identical result. This is what a real "shuffled directory listing"
        determinism test exercises without any filesystem-level mocking."""
        fixture = _generate_bulk_fixture(tmp_path, n_test_files=10, its_per_file=3)
        search_bases = _search_base_list(fixture / "src", fixture)
        files = _discover_snippet_dir_files(
            _TIER2_TEST_DIR_NAMES, search_bases, fixture, ".ts", "src",
            is_example_dir=False)
        assert len(files) > 5, "need multiple files for this proof to mean anything"

        parser = get_parser("typescript")
        func_types = _FUNC_TYPES["typescript"]
        class_types = _CLASS_TYPES.get("typescript", set())

        ordered = _collect_tier_candidates(
            files, parser, "typescript", func_types, class_types, fixture,
            set(), {}, set())

        shuffled = list(reversed(files))  # deterministic-but-different order, no RNG needed
        shuffled_result = _collect_tier_candidates(
            shuffled, parser, "typescript", func_types, class_types, fixture,
            set(), {}, set())

        assert ordered == shuffled_result

    def test_full_extraction_run_twice_on_equivalent_fixtures_is_identical(self, tmp_path):
        """Two independently-built (but content-identical) fixture trees
        must scout to the identical snippet set/order/ids/keys."""
        fixture_a = _generate_bulk_fixture(tmp_path / "a")
        fixture_b = _generate_bulk_fixture(tmp_path / "b")
        parser = get_parser("typescript")

        result_a = extract_snippets(
            parser, "typescript", fixture_a / "src", fixture_a, classes=[], formats=[])
        result_b = extract_snippets(
            parser, "typescript", fixture_b / "src", fixture_b, classes=[], formats=[])

        assert [s["id"] for s in result_a] == [s["id"] for s in result_b]
        assert [s["source_file"] for s in result_a] == [s["source_file"] for s in result_b]
        assert [s["source_function"] for s in result_a] == [s["source_function"] for s in result_b]
        assert [s["snippet_key"] for s in result_a] == [s["snippet_key"] for s in result_b]

    def test_adding_one_test_file_only_adds_new_tier2_entries(self, tmp_path):
        """Add one extra test file (sorted to the END of tier 2's path
        ordering) -- the diff between the two runs' snippet index must show
        ONLY additions, all in tier 2; tier 0 (README) and tier 1
        (examples) entries must be byte-identical."""
        fixture_before = _generate_bulk_fixture(tmp_path / "before", n_test_files=5)
        fixture_after = _generate_bulk_fixture(tmp_path / "after", n_test_files=5)
        # "zzz_" sorts after every "gen_*"/"document.test.ts" path so this
        # is a pure append at the end of tier 2's deterministic order.
        (fixture_after / "test" / "zzz_extra.test.ts").write_text(
            "describe('Extra', () => {\n"
            "  it('extra case one', () => { const z = 1; });\n"
            "  it('extra case two', () => { const z = 2; });\n"
            "});\n",
            encoding="utf-8",
        )

        parser = get_parser("typescript")
        before = extract_snippets(
            parser, "typescript", fixture_before / "src", fixture_before, classes=[], formats=[])
        after = extract_snippets(
            parser, "typescript", fixture_after / "src", fixture_after, classes=[], formats=[])

        assert len(before) < MAX_SNIPPETS, "scenario must not already be saturated"
        assert len(after) == len(before) + 2

        before_keys = [s["snippet_key"] for s in before]
        after_keys = [s["snippet_key"] for s in after]

        tier01_before = [s["snippet_key"] for s in before if not s["source_file"].startswith("test/")]
        tier01_after = [s["snippet_key"] for s in after if not s["source_file"].startswith("test/")]
        assert tier01_before == tier01_after, "tier 0/1 must be untouched by a tier-2-only change"

        assert set(before_keys).issubset(set(after_keys)), "no pre-existing snippet may be evicted"

        new_keys = set(after_keys) - set(before_keys)
        new_entries = [s for s in after if s["snippet_key"] in new_keys]
        assert new_entries
        assert all(s["source_file"].startswith("test/") for s in new_entries), (
            "the only new entries must belong to tier 2"
        )
        assert {s["source_function"] for s in new_entries} == {"extra case one", "extra case two"}


# ---------------------------------------------------------------------------
# snippet_key
# ---------------------------------------------------------------------------

class TestSnippetKey:
    def test_snippet_key_present_and_hex_sha256(self, tmp_path):
        fixture = _copy_ts_fixture(tmp_path / "pkg")
        parser = get_parser("typescript")
        snippets = extract_snippets(
            parser, "typescript", fixture / "src", fixture, classes=[], formats=[])
        assert snippets
        for s in snippets:
            assert re.fullmatch(r"[0-9a-f]{64}", s["snippet_key"]), s["snippet_key"]

    def test_snippet_key_distinguishes_distinct_snippets(self, tmp_path):
        fixture = _copy_ts_fixture(tmp_path / "pkg")
        parser = get_parser("typescript")
        snippets = extract_snippets(
            parser, "typescript", fixture / "src", fixture, classes=[], formats=[])
        keys = [s["snippet_key"] for s in snippets]
        assert len(keys) == len(set(keys))

    def test_normalize_snippet_code_strips_lines_and_collapses_blanks(self):
        raw = "  line1  \n\n\n\n  line2  "
        assert _normalize_snippet_code(raw) == "line1\n\nline2"

    def test_compute_snippet_key_insensitive_to_blank_line_run_length(self):
        k1 = _compute_snippet_key("f.ts", "fn", "line1\n\nline2  ")
        k2 = _compute_snippet_key("f.ts", "fn", "line1\n\n\n\nline2")
        assert k1 == k2

    def test_compute_snippet_key_sensitive_to_real_content_change(self):
        k1 = _compute_snippet_key("f.ts", "fn", "return 1;")
        k2 = _compute_snippet_key("f.ts", "fn", "return 2;")
        assert k1 != k2

    def test_compute_snippet_key_matches_manual_sha256(self):
        import hashlib
        code = "  const x = 1;  \n\n\n  return x;  "
        normalized = _normalize_snippet_code(code)
        expected = hashlib.sha256(
            f"a/b.ts|myFunc|{normalized}".encode("utf-8")).hexdigest()
        assert _compute_snippet_key("a/b.ts", "myFunc", code) == expected
