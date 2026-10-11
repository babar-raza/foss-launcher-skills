"""extraction/snippets.py — Code snippet extraction from test/example dirs.

Extracted from scout.py (step 4.6). Standalone functions usable without the
Scout class.

Public API::

    extract_snippets(parser, language, pkg_root, repo, classes, formats)
        -> list[dict]   # snippet dicts ready for scout output
"""
from __future__ import annotations

import hashlib
import logging
import re
from pathlib import Path
from typing import Any

from extraction.tree_helpers import (
    MAX_FILES,
    _CLASS_TYPES,
    _FILE_EXTENSIONS,
    _FUNC_TYPES,
    _node_name,
    child_by_field,
    collect_nodes,
    node_text,
)

LOG = logging.getLogger(__name__)

MAX_SNIPPETS = 100

_NON_ALNUM_RE = re.compile(r"[^a-z0-9]+")

# TC-MT040-44 (D-5) / MT074 B3: platforms opted into the deterministic tiered
# snippet budget (_extract_snippets_tiered below) instead of the legacy cap-by-
# iteration-order path are DECLARED, not hard-coded: each row of
# config/platform_capabilities.yaml carries a `snippet_budget` capability
#
#     snippet_budget:
#       mode: tiered | legacy
#       languages: [typescript, javascript]   # optional; default [row.language]
#       docs_fence_budget: 0                  # tier-0 slots for docs/**/*.md fences
#       test_tail_reserve: 0                  # tier-2 slots spread over the tail
#       stable_superset: false                # true: tier 2 keeps legacy order (retained PREFIX only)
#
# `languages` is matched against the `language` argument of extract_snippets()
# (the tree-sitter language, e.g. "java"), NOT the platform key. A language
# absent from every row (or `mode: legacy`) takes the legacy path, whose
# output is byte-identical to before this capability existed (proven by
# test_typescript_snippet_ordering.py / test_snippet_delta_priority.py
# golden-parity tests). scripts/ci/checks/check_platform_capabilities.py
# keeps the YAML and this loader in agreement.
_SNIPPET_BUDGET_MODES = ("legacy", "tiered")
_CAPABILITIES_YAML = (Path(__file__).resolve().parents[1] / "config"
                      / "platform_capabilities.yaml")

# configure() seam (module _cfg_* globals + configure() + autouse fixture).
_cfg_capabilities_path: "Path | None" = None
_cfg_budget_by_language: "dict[str, dict] | None" = None
_budget_cache: "dict[str, dict] | None" = None


def configure(*, capabilities_path: "Path | str | None" = None,
              budget_by_language: "dict[str, dict] | None" = None) -> None:
    """Test/operator hook. `capabilities_path` redirects the YAML read;
    `budget_by_language` injects the resolved mapping directly (bypassing the
    YAML). Calling with no arguments restores production behaviour."""
    global _cfg_capabilities_path, _cfg_budget_by_language, _budget_cache
    _cfg_capabilities_path = Path(capabilities_path) if capabilities_path else None
    _cfg_budget_by_language = budget_by_language
    _budget_cache = None


class SnippetBudgetConfigError(RuntimeError):
    """platform_capabilities.yaml is missing, unreadable, or its
    `snippet_budget` block for the requested language is malformed."""


def _normalize_budget(platform: str, decl: dict) -> dict:
    out: dict = {}
    for knob in ("docs_fence_budget", "test_tail_reserve"):
        v = decl.get(knob, 0)
        if not isinstance(v, int) or isinstance(v, bool) or v < 0:
            raise SnippetBudgetConfigError(
                f"platform_capabilities.yaml: platforms.{platform}.snippet_budget."
                f"{knob}={v!r} must be a non-negative integer. Fix that row in "
                f"scripts/pipeline/config/platform_capabilities.yaml "
                f"(scripts/ci/checks/check_platform_capabilities.py reports it).")
        out[knob] = v
    out["stable_superset"] = bool(decl.get("stable_superset", False))
    return out


def _row_languages(row: dict, decl: dict) -> list:
    languages = decl.get("languages") or [row.get("language")]
    return [str(x) for x in languages if x] if isinstance(languages, (list, tuple)) else []


def parse_snippet_budgets(caps: dict) -> "dict[str, dict]":
    """Resolve a parsed platform_capabilities mapping into
    {language: normalized tiered-budget dict}. Only `mode: tiered` rows
    contribute. Pure and STRICT (a malformed row raises
    SnippetBudgetConfigError) -- used by check_platform_capabilities.py;
    extraction itself resolves ONE language lazily via snippet_budget_for()."""
    out: dict[str, dict] = {}
    for platform, row in sorted((caps.get("platforms") or {}).items()):
        decl = row.get("snippet_budget")
        if not isinstance(decl, dict) or decl.get("mode") != "tiered":
            continue
        norm = _normalize_budget(platform, decl)
        for lang in _row_languages(row, decl):
            out[lang] = dict(norm)
    return out


def _capabilities_doc() -> dict:
    """The raw parsed YAML, read once. Fails LOUD (silently falling back to
    the legacy path would change which snippets a tiered platform harvests
    without any signal) -- but with a message naming the file and the fix."""
    global _budget_cache
    if _budget_cache is None:
        import yaml
        path = _cfg_capabilities_path or _CAPABILITIES_YAML
        try:
            with open(path, encoding="utf-8") as f:
                doc = yaml.safe_load(f)
        except OSError as exc:
            raise SnippetBudgetConfigError(
                f"cannot read {path}: {exc}. extract_snippets needs the platform "
                f"capability contract; restore scripts/pipeline/config/"
                f"platform_capabilities.yaml (git checkout it) or point "
                f"extraction.snippets.configure(capabilities_path=...) at a valid copy.") from exc
        except yaml.YAMLError as exc:
            raise SnippetBudgetConfigError(
                f"{path} is not valid YAML: {exc}. Fix the syntax error "
                f"(scripts/ci/checks/check_platform_capabilities.py shows the "
                f"offending platform) -- every scout run reads this file.") from exc
        if not isinstance(doc, dict):
            raise SnippetBudgetConfigError(
                f"{path} must contain a mapping with a `platforms:` key, got {type(doc).__name__}.")
        _budget_cache = doc
    return _budget_cache


def snippet_budget_for(language: str) -> "dict | None":
    """Tiered-budget config for *language*, or None for the legacy path.

    Resolved LAZILY per language: only rows that claim *language* are
    validated, so a corrupt snippet_budget block for another platform (say
    java) cannot break extraction for a legacy language (say python)."""
    if _cfg_budget_by_language is not None:
        return _cfg_budget_by_language.get(language)
    platforms = _capabilities_doc().get("platforms") or {}
    for platform, row in sorted(platforms.items()):
        decl = row.get("snippet_budget") if isinstance(row, dict) else None
        if not isinstance(decl, dict) or decl.get("mode") != "tiered":
            continue
        if language in _row_languages(row, decl):
            return _normalize_budget(platform, decl)
    return None


def snippet_budget_for_all() -> "dict[str, dict]":
    """Copy of the resolved {language: tiered-budget} mapping (strict)."""
    if _cfg_budget_by_language is not None:
        return {k: dict(v) for k, v in _cfg_budget_by_language.items()}
    return parse_snippet_budgets(_capabilities_doc())


def tiered_snippet_languages() -> frozenset:
    """Languages that take the tiered path (derived from the YAML)."""
    return frozenset(snippet_budget_for_all())


# Legacy (non-tiered) directory scan order -- iteration-order dependent by
# construction, unchanged for every platform that does not declare
# `snippet_budget.mode: tiered`.
# Hoisted to module scope (previously an inline literal inside
# extract_snippets) purely so tests can pin the literal without needing to
# re-run extraction; the *values* and *order* are untouched.
_DEFAULT_SNIPPET_DIRS = ["tests", "test", "examples", "example", "samples",
                         "demo", "ApiExamples", "api_examples", "_examples"]
_EXAMPLE_DIR_NAMES = {"examples", "example", "samples", "demo",
                      "ApiExamples", "api_examples", "_examples"}

# TC-MT040-44 tier directory groups (tiered path only).
_TIER1_EXAMPLE_DIR_NAMES = ["examples", "example", "samples", "demo",
                            "ApiExamples", "api_examples", "_examples"]
_TIER2_TEST_DIR_NAMES = ["tests", "test"]

# TC-MT040-16 (G-TS-04b): a file living under a test/tests directory that is
# NOT itself named like a test file (*.test.ts, *.spec.ts, test_*.ts,
# *_test.ts) contributes nothing to snippets -- e.g. `test/helpers/util.ts`
# holds shared test scaffolding, not API-usage evidence, even though an
# `export`ed helper function inside it would otherwise look exactly like a
# legitimate exported-function snippet candidate.
_TS_TEST_FILE_RE = re.compile(r"(?:\.test|\.spec)$|^test_|_test$", re.IGNORECASE)


def _dir_name_matches_pattern(dirname: str, pattern: str) -> bool:
    """True if dirname is a snippet-worthy directory for pattern (e.g. "tests"),
    either by exact match (case-insensitive — preserves the original behavior
    for names like "ApiExamples", "_examples") or by appearing as a WHOLE
    TOKEN once the name is split on non-alphanumeric separators.

    HARDEN-words-net (2026-07-22): words/net's actual test directory is named
    `Aspose.Words.Tests` — a common C#-solution naming convention this
    exact-match-only check could never find (it's not literally named
    "tests"), which silently produced only 1 code snippet for a product this
    size (vs. 100, the cap, for sibling .NET products whose repos happen to
    have a literal `tests/` directory). Token matching catches
    `Aspose.Words.Tests` -> tokens ["aspose","words","tests"] -> "tests"
    matches, while deliberately NOT matching unrelated names that merely
    contain the substring "test" (e.g. "Latest", "Contest" tokenize as single
    words that aren't equal to "test"), and NOT matching `Aspose.Words.TestFx`
    (a test-*framework* helper library, tokenizes to "testfx", not "test" —
    correctly excluded, it holds no example code)."""
    dl = dirname.lower()
    pl = pattern.lower()
    if dl == pl:
        return True
    return pl in _NON_ALNUM_RE.split(dl)


def _is_product_affine(dirname: str, pkg_name: str) -> bool:
    """True if dirname appears to belong to the SAME product/namespace as
    pkg_name (the package root's own directory name), e.g. pkg_name
    "Aspose.Words", dirname "Aspose.Words.Tests" -> True.

    HARDEN-words-net (2026-07-22), found by adversarial re-review of the
    token-matching fix above: words/net's clone has THREE directories that
    token-match "tests" — the real product tests (`Aspose.Words.Tests`), a
    correctly-excluded test-framework helper (`Aspose.Words.TestFx`, doesn't
    token-match at all), and a bundled Java-compat shim's OWN unrelated test
    suite (`Aspose.JavaMs.Tests`). Without this affinity check, directory
    iteration order (alphabetical here) let `Aspose.JavaMs.Tests` exhaust the
    entire MAX_SNIPPETS budget on BouncyCastle/collection-shim tests before
    `Aspose.Words.Tests` was ever reached — worse than the original bug, since
    100 snippets now LOOK like real coverage while containing zero genuine
    Aspose.Words API examples."""
    dl = dirname.lower()
    pl = pkg_name.lower()
    return dl == pl or dl.startswith(pl + ".") or dl.startswith(pl + "_") or dl.startswith(pl + "-")


def _leaf_test_blocks(
    blocks: list[tuple[str, Any, int]],
) -> list[tuple[str, Any, int]]:
    """Drop any test/describe block whose byte range strictly CONTAINS
    another collected block, keeping only leaf blocks.

    TC-MT040-16 (G-TS-04a): a nested ``describe()`` that wraps one or more
    ``it()``/``test()`` blocks is dropped as a snippet in its own right --
    it mostly just repeats what its inner blocks already show, so capturing
    both is a near-duplicate. A ``describe()`` with no collected children
    (nothing nested, or its children were filtered out upstream) is kept,
    since it is then the leaf itself.

    Pure and order-independent: given the SAME set of blocks in any input
    order, the returned leaf set is identical (each block's "is this a
    wrapper" question is answered purely from its own byte range against
    every other block's, never from position in *blocks*).
    """
    def _byte_range(node) -> tuple[int, int]:
        return (node.start_byte, node.end_byte)

    leaves: list[tuple[str, Any, int]] = []
    for name, node, line in blocks:
        s, e = _byte_range(node)
        is_wrapper = False
        for _other_name, other_node, _other_line in blocks:
            if other_node is node:
                continue
            os_, oe = _byte_range(other_node)
            if s <= os_ and e >= oe and (s, e) != (os_, oe):
                is_wrapper = True
                break
        if not is_wrapper:
            leaves.append((name, node, line))
    return leaves


def _collect_snippet_functions(
    root,
    language: str,
    func_types: set,
    class_types: set,
    source_text: str,
    is_example_dir: bool = False,
    file_stem: str = "",
) -> list[tuple[str, Any, int]]:
    """Collect candidate test/example functions from a parsed tree.

    Returns list of (function_name, node, line_number) tuples.
    Language-specific heuristics determine which functions qualify.
    When *is_example_dir* is True, C++ ``main()`` functions are also
    captured — example files use ``main`` rather than test_ naming.

    HARDEN-cpp-smoke-main (2026-07-28, MT012): a real-world C++ idiom found
    live in pdf/cpp's tests/ dir — hand-rolled smoke tests with no gtest
    dependency, just a bare ``int main()`` and a local pass/fail counter
    (e.g. ``document_info_test.cpp``). These live in a "tests" dir, not an
    "examples" dir, so *is_example_dir* is false for them; *file_stem* lets
    the cpp branch recognize the ``*_test``/``*_smoke_test`` filename
    convention as its own signal, independent of directory naming.
    """
    results: list[tuple[str, Any, int]] = []

    if language == "python":
        for fn in collect_nodes(root, func_types):
            fname = _node_name(fn, language)
            if fname and (fname.startswith("test_")
                          or fname.startswith("example_")
                          or fname.startswith("demo_")):
                results.append((fname, fn, fn.start_point[0] + 1))

    elif language in ("java", "csharp"):
        for cn in collect_nodes(root, class_types):
            cname = _node_name(cn, language)
            if not cname:
                continue
            is_test_class = ("Test" in cname or "Example" in cname
                             or "Demo" in cname or "Sample" in cname)
            if not is_test_class:
                continue
            for fn in collect_nodes(cn, func_types):
                fname = _node_name(fn, language)
                if fname and not fname.startswith("_"):
                    results.append((fname, fn, fn.start_point[0] + 1))
        # C# top-level statement files (no class wrapper) in sample dirs:
        # treat root-level expression/statement nodes as a single file snippet.
        if language == "csharp" and is_example_dir and not results:
            non_class_nodes = [
                ch for ch in root.children
                if ch.type not in class_types and ch.type != "using_directive"
                and ch.type not in ("namespace_declaration", "comment",
                                    "extern_alias_directive")
                and not ch.type.endswith("_statement")  # skip isolated stmts
            ]
            # If there is any meaningful code at top level (not just using/ns)
            has_top_level = any(
                ch for ch in root.children
                if ch.type not in ("using_directive", "extern_alias_directive",
                                   "namespace_declaration")
                and ch.type != "comment"
            )
            if has_top_level:
                # Emit the entire root as one "file-level" snippet
                results.append(("(top_level_program)", root, 1))

    elif language == "cpp":
        _gtest_macros = {"TEST", "TEST_F", "TEST_P", "TYPED_TEST"}
        for fn in collect_nodes(root, func_types):
            fname = _node_name(fn, language)
            if not fname:
                # C++ function_definition: name lives in function_declarator child
                for ch in fn.children:
                    if ch.type == "function_declarator":
                        for gch in ch.children:
                            if gch.type == "identifier":
                                fname = node_text(gch)
                                break
                        break
            _is_smoke_test_file = file_stem.lower().endswith(
                ("_test", "_smoke_test"))
            if fname and (fname.startswith("test_")
                          or fname.startswith("Test")
                          or fname in _gtest_macros
                          or (is_example_dir and fname == "main")
                          or (_is_smoke_test_file and fname == "main")):
                results.append((fname, fn, fn.start_point[0] + 1))

    elif language in ("typescript", "javascript"):
        # TC-MT040-16 (G-TS-04b): a file under a test/tests directory
        # (is_example_dir False) that is NOT itself named like a test file
        # contributes nothing -- e.g. `test/helpers/util.ts` holds shared
        # scaffolding, not API-usage evidence, even though its exported
        # helper functions would otherwise look exactly like legitimate
        # exported-function snippet candidates below.
        if not is_example_dir and file_stem and not _TS_TEST_FILE_RE.search(file_stem):
            return results

        for fn in collect_nodes(root, func_types):
            fname = _node_name(fn, language)
            if not fname:
                continue
            parent = fn.parent
            is_exported = (parent and parent.type == "export_statement")
            is_test_fn = (fname.startswith("test")
                          or fname.startswith("example")
                          or fname.startswith("demo"))
            if is_exported or is_test_fn:
                results.append((fname, fn, fn.start_point[0] + 1))

        _test_block_names = {"test", "it", "describe"}
        _blocks: list[tuple[str, Any, int]] = []
        for call_node in collect_nodes(root, {"call_expression"}):
            fn_part = child_by_field(call_node, "function")
            if fn_part and node_text(fn_part) in _test_block_names:
                args = child_by_field(call_node, "arguments")
                if args and args.children:
                    desc = ""
                    for ch in args.children:
                        if ch.type in ("string", "template_string"):
                            desc = node_text(ch).strip("'\"` ")
                            break
                    block_name = desc[:60] or node_text(fn_part)
                    _blocks.append(
                        (block_name, call_node,
                         call_node.start_point[0] + 1))
        # TC-MT040-16 (G-TS-04a): leaf-only -- drop a describe() wrapper
        # that strictly contains other collected it()/test() blocks so it
        # is never captured as a near-duplicate of its own children.
        results.extend(_leaf_test_blocks(_blocks))

    elif language == "go":
        # Go testable examples: ExampleXxx functions in *_test.go files.
        # main() functions in _examples/ dirs (is_example_dir=True).
        for fn in collect_nodes(root, func_types):
            fname = _node_name(fn, language)
            if not fname:
                continue
            if fname.startswith("Example"):
                results.append((fname, fn, fn.start_point[0] + 1))
            elif is_example_dir and fname == "main":
                results.append((fname, fn, fn.start_point[0] + 1))

    elif language == "rust":
        # Rust tests are #[test]-attributed fns (usually inside an inline
        # `#[cfg(test)] mod tests` block in the src file itself); examples/
        # files use main(). The #[test] attribute is an attribute_item
        # sibling immediately preceding the function_item.
        _rust_test_attr_re = re.compile(r"#\s*\[\s*(?:\w+(?:::\w+)*::)?test\b")
        for fn in collect_nodes(root, {"function_item"}):
            fname = _node_name(fn, language)
            if not fname:
                continue
            has_test_attr = False
            cur = fn.prev_named_sibling
            while cur is not None and cur.type == "attribute_item":
                if _rust_test_attr_re.search(node_text(cur)):
                    has_test_attr = True
                    break
                cur = cur.prev_named_sibling
            if (has_test_attr or fname.startswith("test_")
                    or fname.startswith("example_")):
                results.append((fname, fn, fn.start_point[0] + 1))
            elif is_example_dir and fname == "main":
                results.append((fname, fn, fn.start_point[0] + 1))

    return results


def extract_snippets(
    parser,
    language: str,
    pkg_root: Path,
    repo: Path,
    classes: list[dict],
    formats: list[dict],
) -> list[dict]:
    """Extract function-level snippets from test/example directories.

    For each test/example function found, records which API classes and
    methods it references (cross-referenced against *classes*) and which
    file format names appear in *formats*.  Also extracts README code
    blocks as whole-file snippets.  Capped at MAX_SNIPPETS per product.

    Returns a list of snippet dicts.

    TC-MT040-44 (D-5): languages whose platform row declares
    `snippet_budget: {mode: tiered}` in platform_capabilities.yaml are
    dispatched to the deterministic tiered budget (_extract_snippets_tiered)
    instead of this legacy cap-by-iteration-order path. Every other
    platform's code below is completely untouched -- verified byte-identical
    by test_typescript_snippet_ordering.py's golden parity test.
    """
    _tiered_budget = snippet_budget_for(language)
    if _tiered_budget is not None:
        return _extract_snippets_tiered(
            parser, language, pkg_root, repo, classes, formats,
            budget=_tiered_budget)

    # Build lookup sets from already-extracted api_surface
    api_class_names: set[str] = set()
    api_method_index: dict[str, set[str]] = {}
    for cls in classes:
        cname = cls.get("name", "")
        if not cname or cls.get("kind") == "function":
            continue
        api_class_names.add(cname)
        meths: set[str] = set()
        for m in cls.get("methods", []):
            if isinstance(m, dict) and m.get("name"):
                meths.add(m["name"])
        api_method_index[cname] = meths

    format_names: set[str] = set()
    for fmt in formats:
        fname = fmt.get("format", "")
        if fname:
            format_names.add(fname.lower())

    snippet_dirs = list(_DEFAULT_SNIPPET_DIRS)
    _example_dirs = set(_EXAMPLE_DIR_NAMES)
    ext = _FILE_EXTENSIONS.get(language, ".py")
    func_types = _FUNC_TYPES.get(language, set())
    class_types = _CLASS_TYPES.get(language, set())

    # Build search base list: walk from pkg_root up to repo root
    _search_bases: list[Path] = []
    _p = pkg_root
    while True:
        try:
            _p.relative_to(repo)
            _search_bases.append(_p)
        except ValueError:
            pass
        if _p == repo or _p.parent == _p:
            break
        _p = _p.parent
    if repo not in _search_bases:
        _search_bases.append(repo)

    snippets: list[dict] = []
    snippet_counter = 0
    _pkg_name = pkg_root.name

    for sdir in snippet_dirs:
        _visited: set[Path] = set()
        for _base in _search_bases:
            # Exact join (original behavior — literal "tests"/"ApiExamples"/
            # etc. as a direct child) PLUS any direct child matching sdir as
            # a whole token (catches compound names like Aspose.Words.Tests).
            #
            # Token matches are affinity-filtered: prefer directories sharing
            # the package's own namespace prefix (Aspose.Words.Tests, for
            # pkg_root "Aspose.Words") over unrelated siblings that happen to
            # ALSO token-match (Aspose.JavaMs.Tests, a bundled dependency's
            # own test suite) — otherwise the FIRST-visited match can exhaust
            # the whole MAX_SNIPPETS budget before the real product's tests
            # are ever reached (found by adversarial re-review; see
            # _is_product_affine's docstring).
            _candidate_dirs: list[Path] = []
            _exact = _base / sdir
            if _exact.is_dir():
                _candidate_dirs.append(_exact)
            if _base.is_dir():
                try:
                    _children = list(_base.iterdir())
                except OSError:
                    _children = []
                _token_matches = [
                    c for c in _children
                    if c != _exact and c.is_dir() and _dir_name_matches_pattern(c.name, sdir)
                ]
                if _token_matches:
                    _affine = [c for c in _token_matches if _is_product_affine(c.name, _pkg_name)]
                    if _affine:
                        _candidate_dirs.extend(sorted(_affine))
                    else:
                        if len(_token_matches) > 1:
                            LOG.warning(
                                "extract_snippets: %d directories token-match "
                                "%r under %s with no clear product-affine "
                                "match (pkg_root=%s) -- using all of them: %s. "
                                "Snippet coverage may be diluted by unrelated "
                                "dependencies' test/example code.",
                                len(_token_matches), sdir, _base, _pkg_name,
                                [c.name for c in _token_matches],
                            )
                        _candidate_dirs.extend(sorted(_token_matches))

            for d in _candidate_dirs:
                if d in _visited:
                    continue
                _visited.add(d)
                files = sorted(d.rglob(f"*{ext}"))[:MAX_FILES]
                for fpath in files:
                    if snippet_counter >= MAX_SNIPPETS:
                        break
                    rel = str(fpath.relative_to(repo)).replace("\\", "/")
                    try:
                        src = fpath.read_bytes()
                    except OSError:
                        continue
                    tree = parser.parse(src)
                    text = src.decode("utf-8", errors="replace")
                    root = tree.root_node

                    func_nodes = _collect_snippet_functions(
                        root, language, func_types, class_types, text,
                        is_example_dir=(sdir in _example_dirs),
                        file_stem=fpath.stem)

                    for fn_name, fn_node, fn_line in func_nodes:
                        if snippet_counter >= MAX_SNIPPETS:
                            break
                        code = node_text(fn_node)
                        if not code.strip():
                            continue

                        classes_used: list[str] = []
                        methods_used: list[str] = []
                        formats_ref: list[str] = []

                        code_lower = code.lower()
                        for cname in api_class_names:
                            if cname in code:
                                classes_used.append(cname)
                                for mname in api_method_index.get(cname, set()):
                                    if (f"{cname}.{mname}" in code
                                            or f".{mname}(" in code):
                                        methods_used.append(f"{cname}.{mname}")

                        for fmt_name in format_names:
                            if fmt_name in code_lower:
                                formats_ref.append(fmt_name)

                        snippet_id = f"snippet_{snippet_counter + 1:03d}"
                        snippets.append({
                            "id": snippet_id,
                            "file": f"{snippet_id}{ext}",
                            "source_file": rel,
                            "source_function": fn_name,
                            "source_line": fn_line,
                            "language": language,
                            "code": code[:5000],
                            "valid": not fn_node.has_error,
                            "classes_used": sorted(set(classes_used)),
                            "methods_used": sorted(set(methods_used)),
                            "formats_referenced": sorted(set(formats_ref)),
                        })
                        snippet_counter += 1

        if snippet_counter >= MAX_SNIPPETS:
            break

    # Go-specific: scan *_test.go at package/repo root for ExampleXxx funcs.
    # Go testable examples live in *_test.go files alongside the package source,
    # not inside a tests/ subdirectory — so the snippet_dirs loop misses them.
    if language == "go" and snippet_counter < MAX_SNIPPETS:
        _visited_test: set[Path] = set()
        for _base in _search_bases:
            for test_file in sorted(_base.glob("*_test.go"))[:MAX_FILES]:
                if test_file in _visited_test:
                    continue
                _visited_test.add(test_file)
                if snippet_counter >= MAX_SNIPPETS:
                    break
                rel = str(test_file.relative_to(repo)).replace("\\", "/")
                try:
                    src = test_file.read_bytes()
                except OSError:
                    continue
                tree = parser.parse(src)
                text = src.decode("utf-8", errors="replace")
                root = tree.root_node
                func_nodes = _collect_snippet_functions(
                    root, language, func_types, class_types, text,
                    is_example_dir=False)
                for fn_name, fn_node, fn_line in func_nodes:
                    if snippet_counter >= MAX_SNIPPETS:
                        break
                    if any(s.get("source_function") == fn_name for s in snippets):
                        continue
                    code = node_text(fn_node)
                    if not code.strip():
                        continue

                    classes_used: list[str] = []
                    methods_used: list[str] = []
                    formats_ref: list[str] = []
                    code_lower = code.lower()
                    for cname in api_class_names:
                        if cname in code:
                            classes_used.append(cname)
                            for mname in api_method_index.get(cname, set()):
                                if (f"{cname}.{mname}" in code
                                        or f".{mname}(" in code):
                                    methods_used.append(f"{cname}.{mname}")
                    for fmt_name in format_names:
                        if fmt_name in code_lower:
                            formats_ref.append(fmt_name)

                    snippet_id = f"snippet_{snippet_counter + 1:03d}"
                    snippets.append({
                        "id": snippet_id,
                        "file": f"{snippet_id}{ext}",
                        "source_file": rel,
                        "source_function": fn_name,
                        "source_line": fn_line,
                        "language": language,
                        "code": code[:5000],
                        "valid": not fn_node.has_error,
                        "classes_used": sorted(set(classes_used)),
                        "methods_used": sorted(set(methods_used)),
                        "formats_referenced": sorted(set(formats_ref)),
                    })
                    snippet_counter += 1

    # Rust-specific: scan src files for inline #[cfg(test)] mod tests blocks.
    # Rust unit tests conventionally live alongside the code they test, not in
    # a tests/ subdirectory — the snippet_dirs loop never visits src/.
    if language == "rust" and snippet_counter < MAX_SNIPPETS:
        for src_file in sorted(pkg_root.rglob("*.rs"))[:MAX_FILES]:
            if snippet_counter >= MAX_SNIPPETS:
                break
            rel = str(src_file.relative_to(repo)).replace("\\", "/")
            try:
                src = src_file.read_bytes()
            except OSError:
                continue
            if b"#[test]" not in src and b"#[cfg(test)]" not in src:
                continue
            tree = parser.parse(src)
            text = src.decode("utf-8", errors="replace")
            root = tree.root_node
            func_nodes = _collect_snippet_functions(
                root, language, func_types, class_types, text,
                is_example_dir=False)
            for fn_name, fn_node, fn_line in func_nodes:
                if snippet_counter >= MAX_SNIPPETS:
                    break
                if any(s.get("source_function") == fn_name for s in snippets):
                    continue
                code = node_text(fn_node)
                if not code.strip():
                    continue

                classes_used = []
                methods_used = []
                formats_ref = []
                code_lower = code.lower()
                for cname in api_class_names:
                    if cname in code:
                        classes_used.append(cname)
                        for mname in api_method_index.get(cname, set()):
                            if (f"{cname}.{mname}" in code
                                    or f".{mname}(" in code):
                                methods_used.append(f"{cname}.{mname}")
                for fmt_name in format_names:
                    if fmt_name in code_lower:
                        formats_ref.append(fmt_name)

                snippet_id = f"snippet_{snippet_counter + 1:03d}"
                snippets.append({
                    "id": snippet_id,
                    "file": f"{snippet_id}{ext}",
                    "source_file": rel,
                    "source_function": fn_name,
                    "source_line": fn_line,
                    "language": language,
                    "code": code[:5000],
                    "valid": not fn_node.has_error,
                    "classes_used": sorted(set(classes_used)),
                    "methods_used": sorted(set(methods_used)),
                    "formats_referenced": sorted(set(formats_ref)),
                })
                snippet_counter += 1

    # README fenced code blocks (as whole-file snippets)
    for readme_name in ("README.md", "readme.md", "README.rst"):
        if snippet_counter >= MAX_SNIPPETS:
            break
        readme = repo / readme_name
        if readme.exists():
            try:
                text = readme.read_text(encoding="utf-8", errors="replace")
            except OSError:
                continue
            lang_names = {language}
            if language == "csharp":
                lang_names.update({"csharp", "cs", "c#"})
            if language == "javascript":
                lang_names.update({"javascript", "js"})
            if language == "typescript":
                lang_names.update({"typescript", "ts"})
            if language == "python":
                lang_names.update({"python", "py"})
            if language == "java":
                lang_names.add("java")
            if language == "cpp":
                lang_names.update({"cpp", "c++"})
            if language == "rust":
                lang_names.update({"rust", "rs"})

            fence_pattern = re.compile(
                r"```(" + "|".join(re.escape(n) for n in lang_names)
                + r")\s*\n(.*?)```", re.DOTALL | re.IGNORECASE)
            for m in fence_pattern.finditer(text):
                if snippet_counter >= MAX_SNIPPETS:
                    break
                code = m.group(2)
                t = parser.parse(code.encode("utf-8"))
                valid = not t.root_node.has_error

                classes_used = [c for c in api_class_names if c in code]
                methods_used = []
                for cname in classes_used:
                    for mname in api_method_index.get(cname, set()):
                        if f"{cname}.{mname}" in code or f".{mname}(" in code:
                            methods_used.append(f"{cname}.{mname}")
                formats_ref = [f for f in format_names if f in code.lower()]

                snippet_id = f"snippet_{snippet_counter + 1:03d}"
                snippets.append({
                    "id": snippet_id,
                    "file": f"{snippet_id}{ext}",
                    "source_file": readme_name,
                    "source_function": "(readme_block)",
                    "source_line": text[:m.start()].count("\n") + 1,
                    "language": language,
                    "code": code[:5000],
                    "valid": valid,
                    "classes_used": sorted(set(classes_used)),
                    "methods_used": sorted(set(methods_used)),
                    "formats_referenced": sorted(set(formats_ref)),
                })
                snippet_counter += 1
            break

    return snippets


# ---------------------------------------------------------------------------
# TC-MT040-44 (D-5): deterministic tiered snippet budget
# ---------------------------------------------------------------------------
#
# Tier 0 -- README code fences (<=10)
# Tier 1 -- curated examples/samples directories (<=60)
# Tier 2 -- tests (remainder up to MAX_SNIPPETS, unchanged total cap)
#
# Applies only to languages declared `snippet_budget.mode: tiered` in
# platform_capabilities.yaml. Within each tier,
# candidates are sorted deterministically by (source path, then source line)
# -- NEVER by filesystem/directory-listing iteration order -- so re-running
# scout on an unchanged repo always produces an identical snippet set and
# order. "Product-affinity" (the words/net Aspose.Words.Tests-vs-
# Aspose.JavaMs.Tests problem _is_product_affine solves) is already applied
# one layer up, at directory-selection time in _discover_snippet_dir_files
# (identical rule to the legacy path); once a directory is selected as a
# genuine candidate, ordering the affinity question is settled, and the
# remaining tie-break is exactly the plan's stated fallback: path, then
# line number.


def _normalize_snippet_code(code: str) -> str:
    """Normalize snippet code for `snippet_key` hashing: strip leading/
    trailing whitespace on every line, and collapse runs of consecutive
    blank lines down to a single blank line. Deliberately simple/stable --
    the goal is a key that survives incidental re-indentation or blank-line
    churn upstream, not a semantic/AST-level normalization."""
    normalized_lines: list[str] = []
    prev_blank = False
    for raw_line in code.splitlines():
        line = raw_line.strip()
        if line == "":
            if prev_blank:
                continue
            prev_blank = True
        else:
            prev_blank = False
        normalized_lines.append(line)
    return "\n".join(normalized_lines)


def _compute_snippet_key(source_file: str, source_function: str, code: str) -> str:
    """sha256 of `source_file|source_function|normalized_code` -- an
    additive identity for a snippet's CONTENT, independent of its
    positional `snippet_NNN` id (which promote.py renumbers on merge
    anyway). Its purpose is to make additions/evictions show up as an
    explicit diff (e.g. in merge_report.md) even though ids are positional.
    """
    normalized = _normalize_snippet_code(code)
    payload = f"{source_file}|{source_function}|{normalized}"
    return hashlib.sha256(payload.encode("utf-8")).hexdigest()


def _snippet_cross_refs(
    code: str,
    api_class_names: set[str],
    api_method_index: dict[str, set[str]],
    format_names: set[str],
) -> tuple[list[str], list[str], list[str]]:
    """Same classes_used/methods_used/formats_referenced logic as the
    legacy per-snippet blocks in extract_snippets, factored out as a pure
    helper for the tiered path (kept separate from -- not shared with --
    the legacy code so the legacy path is never at risk of an accidental
    behavior change from this refactor)."""
    classes_used: list[str] = []
    methods_used: list[str] = []
    for cname in api_class_names:
        if cname in code:
            classes_used.append(cname)
            for mname in api_method_index.get(cname, set()):
                if f"{cname}.{mname}" in code or f".{mname}(" in code:
                    methods_used.append(f"{cname}.{mname}")
    code_lower = code.lower()
    formats_ref = [f for f in format_names if f in code_lower]
    return sorted(set(classes_used)), sorted(set(methods_used)), sorted(set(formats_ref))


def _search_base_list(pkg_root: Path, repo: Path) -> list[Path]:
    """Walk from pkg_root up to repo, collecting every directory in between
    (inclusive) as a search base -- identical logic to the inline block in
    extract_snippets, factored out for reuse by the tiered path."""
    search_bases: list[Path] = []
    cur = pkg_root
    while True:
        try:
            cur.relative_to(repo)
            search_bases.append(cur)
        except ValueError:
            pass
        if cur == repo or cur.parent == cur:
            break
        cur = cur.parent
    if repo not in search_bases:
        search_bases.append(repo)
    return search_bases


def _discover_snippet_dir_files(
    sdir_names: list[str],
    search_bases: list[Path],
    repo: Path,
    ext: str,
    pkg_name: str,
    *,
    is_example_dir: bool,
) -> list[tuple[Path, bool]]:
    """Find every *ext file under any directory matching a name in
    *sdir_names* (exact match, or a product-affine token match -- the same
    directory-resolution rules as the legacy path's nested loop, see
    _dir_name_matches_pattern / _is_product_affine), across every search
    base. Returns (file_path, is_example_dir) pairs.

    The RETURN ORDER of this function is intentionally not the final
    snippet order -- callers must sort explicitly (see the callers in
    _extract_snippets_tiered) before assigning snippet ids. This is the
    determinism seam: a caller/test may pass `sdir_names`/`search_bases` in
    any order, or shuffle the returned list, and the final tiered output is
    unaffected because ordering is decided later by an explicit sort key,
    never by this function's (or the filesystem's) iteration order.
    """
    found: list[tuple[Path, bool]] = []
    visited: set[Path] = set()
    for sdir in sdir_names:
        for base in search_bases:
            candidate_dirs: list[Path] = []
            exact = base / sdir
            if exact.is_dir():
                candidate_dirs.append(exact)
            if base.is_dir():
                try:
                    children = list(base.iterdir())
                except OSError:
                    children = []
                token_matches = [
                    c for c in children
                    if c != exact and c.is_dir() and _dir_name_matches_pattern(c.name, sdir)
                ]
                if token_matches:
                    affine = [c for c in token_matches if _is_product_affine(c.name, pkg_name)]
                    if affine:
                        candidate_dirs.extend(sorted(affine))
                    else:
                        if len(token_matches) > 1:
                            LOG.warning(
                                "_discover_snippet_dir_files: %d directories "
                                "token-match %r under %s with no clear "
                                "product-affine match (pkg_root=%s) -- using "
                                "all of them: %s.",
                                len(token_matches), sdir, base, pkg_name,
                                [c.name for c in token_matches],
                            )
                        candidate_dirs.extend(sorted(token_matches))
            for d in candidate_dirs:
                if d in visited:
                    continue
                visited.add(d)
                for fpath in sorted(d.rglob(f"*{ext}"))[:MAX_FILES]:
                    found.append((fpath, is_example_dir))
    return found


def _collect_tier_candidates(
    files: list[tuple[Path, bool]],
    parser,
    language: str,
    func_types: set,
    class_types: set,
    repo: Path,
    api_class_names: set[str],
    api_method_index: dict[str, set[str]],
    format_names: set[str],
    *,
    preserve_discovery_order: bool = False,
) -> list[dict]:
    """Parse every file in *files* (in WHATEVER order they arrive -- see
    _discover_snippet_dir_files), collect candidate snippet functions/blocks
    from each (hygiene-filtered and leaf-only-filtered by
    _collect_snippet_functions itself), and return them sorted
    deterministically by (source path, source line, source function). This
    sort is what makes the tier's output independent of *files*' input
    order -- the determinism seam TC-MT040-44 requires: a test can pass
    `files` shuffled and still get an identical result.

    MT074 B3: with *preserve_discovery_order* the final sort is skipped and
    candidates stay in `files` order (then in-file collection order) -- the
    exact order the legacy path harvested them, which
    `_discover_snippet_dir_files` already makes deterministic (sdir order ->
    search-base order -> sorted directories -> sorted files). Used only by a
    row declaring `stable_superset: true`, so the old selection is a retained
    prefix of the new one.
    """
    raw: list[dict] = []
    seen: set[Path] = set()
    for fpath, is_example_dir in files:
        if fpath in seen:
            continue
        seen.add(fpath)
        try:
            src = fpath.read_bytes()
        except OSError:
            continue
        tree = parser.parse(src)
        text = src.decode("utf-8", errors="replace")
        root = tree.root_node
        func_nodes = _collect_snippet_functions(
            root, language, func_types, class_types, text,
            is_example_dir=is_example_dir, file_stem=fpath.stem)
        if not func_nodes:
            continue
        rel = str(fpath.relative_to(repo)).replace("\\", "/")
        for fn_name, fn_node, fn_line in func_nodes:
            code = node_text(fn_node)
            if not code.strip():
                continue
            classes_used, methods_used, formats_ref = _snippet_cross_refs(
                code, api_class_names, api_method_index, format_names)
            raw.append({
                "source_file": rel,
                "source_function": fn_name,
                "source_line": fn_line,
                "language": language,
                "code": code,
                "valid": not fn_node.has_error,
                "classes_used": classes_used,
                "methods_used": methods_used,
                "formats_referenced": formats_ref,
            })
    if not preserve_discovery_order:
        raw.sort(key=lambda e: (e["source_file"].lower(), e["source_line"], e["source_function"]))
    return raw


def _collect_readme_fence_entries(
    parser,
    language: str,
    repo: Path,
    api_class_names: set[str],
    api_method_index: dict[str, set[str]],
    format_names: set[str],
) -> list[dict]:
    """Tier 0 candidates: README code fences in the product's own language,
    in document order (already deterministic -- a single file, read once)."""
    entries: list[dict] = []
    for readme_name in ("README.md", "readme.md", "README.rst"):
        readme = repo / readme_name
        if not readme.exists():
            continue
        try:
            text = readme.read_text(encoding="utf-8", errors="replace")
        except OSError:
            continue
        lang_names = _fence_lang_names(language)
        fence_pattern = re.compile(
            r"```(" + "|".join(re.escape(n) for n in lang_names)
            + r")\s*\n(.*?)```", re.DOTALL | re.IGNORECASE)
        for m in fence_pattern.finditer(text):
            code = m.group(2)
            t = parser.parse(code.encode("utf-8"))
            valid = not t.root_node.has_error
            classes_used, methods_used, formats_ref = _snippet_cross_refs(
                code, api_class_names, api_method_index, format_names)
            entries.append({
                "source_file": readme_name,
                "source_function": "(readme_block)",
                "source_line": text[:m.start()].count("\n") + 1,
                "language": language,
                "code": code,
                "valid": valid,
                "classes_used": classes_used,
                "methods_used": methods_used,
                "formats_referenced": formats_ref,
            })
        break
    return entries


def _fence_lang_names(language: str) -> "set[str]":
    """Fence info-string tags that denote *language*. For typescript/
    javascript this is exactly the set the tiered README collector always
    used (byte-identical); other languages add their conventional aliases."""
    names = {language}
    if language == "javascript":
        names.update({"javascript", "js"})
    if language == "typescript":
        names.update({"typescript", "ts"})
    if language == "csharp":
        names.update({"csharp", "cs", "c#"})
    if language == "python":
        names.update({"python", "py"})
    if language == "cpp":
        names.update({"cpp", "c++"})
    if language == "rust":
        names.update({"rust", "rs"})
    return names


_FENCE_OPEN_RE = re.compile(r"^ {0,3}(`{3,}|~{3,})[ \t]*([^\s`]*)")


def _iter_tagged_fences(text: str, lang_names: "set[str]"):
    """Yield (start_line, code) for every CLOSED, language-tagged fenced
    block in *text* whose first info-string token is in *lang_names*.
    Untagged fences, fences of other languages and an unterminated trailing
    fence are skipped. Document order (deterministic)."""
    wanted = {n.lower() for n in lang_names}
    lines = text.splitlines()
    i = 0
    n = len(lines)
    while i < n:
        m = _FENCE_OPEN_RE.match(lines[i])
        if not m:
            i += 1
            continue
        marker, tag = m.group(1), m.group(2).strip("{}.").lower()
        close_re = re.compile(
            r"^ {0,3}" + re.escape(marker[0]) + "{" + str(len(marker)) + r",}[ \t]*$")
        j = i + 1
        while j < n and not close_re.match(lines[j]):
            j += 1
        if j >= n:  # unterminated -> drop, and stop scanning this file
            break
        if tag in wanted:
            yield i + 1, "\n".join(lines[i + 1:j]) + "\n"
        i = j + 1


def _collect_docs_fence_entries(
    parser,
    language: str,
    repo: Path,
    search_bases: "list[Path]",
    api_class_names: "set[str]",
    api_method_index: "dict[str, set[str]]",
    format_names: "set[str]",
    *,
    skip_codes: "set[str] | None" = None,
) -> "list[dict]":
    """MT074 B3 tier-0 candidates: language-tagged fenced code in every
    `docs/**/*.md` under a search base (upstream feature docs are where NEW
    capabilities are first written down -- R4: they never reached snippets).

    Deterministic and independent of any prior knowledge-bundle state: files
    are taken in lower-cased repo-relative path order, fences in document
    order; a fence whose normalized code was already seen (README or an
    earlier docs file) is dropped.
    """
    docs_dirs: list[Path] = []
    for base in search_bases:
        if not base.is_dir():
            continue
        try:
            children = sorted(base.iterdir(), key=lambda p: p.name)
        except OSError:
            continue
        for c in children:
            if c.is_dir() and c.name.lower() == "docs" and c not in docs_dirs:
                docs_dirs.append(c)
    md_files: list[tuple[str, Path]] = []
    seen_files: set[Path] = set()
    for d in docs_dirs:
        for f in d.rglob("*.md"):
            if f in seen_files or not f.is_file():
                continue
            seen_files.add(f)
            md_files.append((str(f.relative_to(repo)).replace("\\", "/"), f))
    md_files.sort(key=lambda t: (t[0].lower(), t[0]))
    lang_names = _fence_lang_names(language)
    seen_codes = set(skip_codes or ())
    entries: list[dict] = []
    for rel, fpath in md_files[:MAX_FILES]:
        try:
            text = fpath.read_text(encoding="utf-8", errors="replace")
        except OSError:
            continue
        for line, code in _iter_tagged_fences(text, lang_names):
            if not code.strip():
                continue
            norm = _normalize_snippet_code(code)
            if norm in seen_codes:
                continue
            seen_codes.add(norm)
            t = parser.parse(code.encode("utf-8"))
            classes_used, methods_used, formats_ref = _snippet_cross_refs(
                code, api_class_names, api_method_index, format_names)
            entries.append({
                "source_file": rel,
                "source_function": "(docs_block)",
                "source_line": line,
                "language": language,
                "code": code,
                "valid": not t.root_node.has_error,
                "classes_used": classes_used,
                "methods_used": methods_used,
                "formats_referenced": formats_ref,
            })
    return entries


def _spread_pick(items: list, k: int) -> list:
    """Deterministically pick *k* items spread evenly (path order preserved)
    across *items*: the midpoint of each of k equal segments. Returns all of
    *items* when len(items) <= k. Pure function of (len, k)."""
    n = len(items)
    if k <= 0:
        return []
    if n <= k:
        return list(items)
    return [items[(2 * i + 1) * n // (2 * k)] for i in range(k)]


def _finalize_snippet(payload: dict, counter: int, ext: str) -> dict:
    """Assign the positional snippet_NNN id/file plus the additive
    snippet_key, truncate code to the 5000-char cap -- the same shape the
    legacy path emits, plus `snippet_key`."""
    snippet_id = f"snippet_{counter:03d}"
    key = _compute_snippet_key(
        payload["source_file"], payload["source_function"], payload["code"])
    return {
        "id": snippet_id,
        "file": f"{snippet_id}{ext}",
        "source_file": payload["source_file"],
        "source_function": payload["source_function"],
        "source_line": payload["source_line"],
        "language": payload["language"],
        "code": payload["code"][:5000],
        "valid": payload["valid"],
        "classes_used": payload["classes_used"],
        "methods_used": payload["methods_used"],
        "formats_referenced": payload["formats_referenced"],
        "snippet_key": key,
    }


def _extract_snippets_tiered(
    parser,
    language: str,
    pkg_root: Path,
    repo: Path,
    classes: list[dict],
    formats: list[dict],
    budget: "dict | None" = None,
) -> list[dict]:
    """TC-MT040-44 (D-5) tiered snippet budget for languages declared
    `snippet_budget.mode: tiered` in platform_capabilities.yaml. See the
    module comment block above for the tier definitions.

    MT074 B3 -- *budget* (the language's declared config) adds OPT-IN,
    default-off knobs, so a row that sets none (typescript/javascript) is
    byte-identical to the pre-B3 behaviour:

      docs_fence_budget  tier 0 also takes up to N language-tagged fences
                         from docs/**/*.md, AFTER the (<=10) README fences
                         and before any example/test (new-capability docs
                         first).
      test_tail_reserve  tier 2 keeps the first (budget - R) candidates in
                         tier-2 order and spends the last R slots on
                         candidates spread evenly across the REMAINDER
                         (see _spread_pick), so tests in later-sorting files
                         (newer features) are reached.
      stable_superset    tier-2 order is the LEGACY discovery order
                         (`tests/` before `test/`, then sorted paths)
                         instead of one global (path, line) sort.

    EXACTLY what is guaranteed -- and what is not (pinned by
    test_snippet_delta_priority.TestStableSupersetFlagIsPinned):

      * Only a RETAINED PREFIX inside tier 2. With stable_superset the first
        (tier-2 budget - test_tail_reserve) snippets of the legacy
        selection survive, in order, where tier-2 budget = MAX_SNIPPETS -
        README fences - docs fences - examples. Examples of the retained
        share of a full 100-snippet legacy selection (reserve 15): 85/100
        for a tree with no README/docs/examples; 56/100 for a real tree
        that also contributes 29 README+docs fences (pdf/java).
      * It is NOT a full superset when the cap binds: the legacy tail
        beyond that prefix is evicted (in reverse tier-2 order) in favour
        of README/docs fences, curated examples and the tail picks.
      * Curated examples (tier 1) are placed BEFORE tests, so a tree that
        has examples loses legacy tests to them by design.
      * Without stable_superset the legacy prefix is not preserved at all
        when both `tests/` and `test/` exist (the global sort puts
        `test/` first); the flag is what keeps it.
      * Only when the whole candidate set fits under MAX_SNIPPETS is the
        new SET a superset of the old one (order may differ).

    Everything is a pure function of the repo tree -- never of prior
    knowledge-bundle state.
    """
    budget = budget or {}
    docs_fence_budget = max(0, int(budget.get("docs_fence_budget", 0)))
    test_tail_reserve = max(0, int(budget.get("test_tail_reserve", 0)))
    stable_superset = bool(budget.get("stable_superset", False))
    api_class_names: set[str] = set()
    api_method_index: dict[str, set[str]] = {}
    for cls in classes:
        cname = cls.get("name", "")
        if not cname or cls.get("kind") == "function":
            continue
        api_class_names.add(cname)
        meths: set[str] = set()
        for m in cls.get("methods", []):
            if isinstance(m, dict) and m.get("name"):
                meths.add(m["name"])
        api_method_index[cname] = meths

    format_names: set[str] = set()
    for fmt in formats:
        fname = fmt.get("format", "")
        if fname:
            format_names.add(fname.lower())

    ext = _FILE_EXTENSIONS.get(language, ".ts")
    func_types = _FUNC_TYPES.get(language, set())
    class_types = _CLASS_TYPES.get(language, set())
    search_bases = _search_base_list(pkg_root, repo)
    pkg_name = pkg_root.name

    snippets: list[dict] = []
    counter = 0

    # ---- Tier 0: README code fences (<=10) ----
    readme_entries = _collect_readme_fence_entries(
        parser, language, repo, api_class_names, api_method_index, format_names)
    for entry in readme_entries[:10]:
        if counter >= MAX_SNIPPETS:
            break
        counter += 1
        snippets.append(_finalize_snippet(entry, counter, ext))

    # ---- Tier 0b (opt-in): docs/**/*.md fenced code ----
    if docs_fence_budget and counter < MAX_SNIPPETS:
        readme_codes = {_normalize_snippet_code(e["code"]) for e in readme_entries}
        docs_entries = _collect_docs_fence_entries(
            parser, language, repo, search_bases, api_class_names,
            api_method_index, format_names, skip_codes=readme_codes)
        for entry in docs_entries[:docs_fence_budget]:
            if counter >= MAX_SNIPPETS:
                break
            counter += 1
            snippets.append(_finalize_snippet(entry, counter, ext))

    # ---- Tier 1: curated examples/samples (<=60) ----
    if counter < MAX_SNIPPETS:
        tier1_files = _discover_snippet_dir_files(
            _TIER1_EXAMPLE_DIR_NAMES, search_bases, repo, ext, pkg_name,
            is_example_dir=True)
        tier1_candidates = _collect_tier_candidates(
            tier1_files, parser, language, func_types, class_types, repo,
            api_class_names, api_method_index, format_names)
        tier1_budget = min(60, MAX_SNIPPETS - counter)
        for entry in tier1_candidates[:tier1_budget]:
            counter += 1
            snippets.append(_finalize_snippet(entry, counter, ext))

    # ---- Tier 2: tests (remainder up to MAX_SNIPPETS) ----
    if counter < MAX_SNIPPETS:
        tier2_files = _discover_snippet_dir_files(
            _TIER2_TEST_DIR_NAMES, search_bases, repo, ext, pkg_name,
            is_example_dir=False)
        tier2_candidates = _collect_tier_candidates(
            tier2_files, parser, language, func_types, class_types, repo,
            api_class_names, api_method_index, format_names,
            preserve_discovery_order=stable_superset)
        tier2_budget = MAX_SNIPPETS - counter
        if test_tail_reserve and len(tier2_candidates) > tier2_budget:
            reserve = min(test_tail_reserve, tier2_budget)
            head = tier2_candidates[:tier2_budget - reserve]
            tail = _spread_pick(tier2_candidates[tier2_budget - reserve:], reserve)
            tier2_selected = head + tail
        else:
            tier2_selected = tier2_candidates[:tier2_budget]
        for entry in tier2_selected:
            counter += 1
            snippets.append(_finalize_snippet(entry, counter, ext))

    return snippets
