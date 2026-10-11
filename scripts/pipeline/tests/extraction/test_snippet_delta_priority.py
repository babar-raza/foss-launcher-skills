"""MT074 B3 (R4): new-capability code must reach snippets.

Covers extraction/snippets.py:
  - the capability-driven tiered selection (platform_capabilities.yaml
    `snippet_budget`, loaded by snippet_budget_for / parse_snippet_budgets)
  - the docs/**/*.md language-tagged fence collector (tier 0b)
  - the tier-2 `test_tail_reserve` + `stable_superset` selection rule:
    previously harvested snippets are a retained prefix, the last R slots are
    spread across the candidates that sort after the cut
  - golden parity: a language NOT opted in (and typescript/javascript, opted
    in with both B3 knobs off) is unaffected by docs/ fences or tail reserve
  - scripts/ci/checks/check_platform_capabilities.py::check_snippet_budget

Every behavioural test is parametrized over a Java fixture AND a Python
fixture (generality gate G-1: no per-language special case in the code under
test; the YAML row is the only thing that names a language).
"""
from __future__ import annotations

import copy
import shutil
import sys
from pathlib import Path

import pytest
import yaml

# sys.path is set by tests/conftest.py -- no manual insert needed here.
from extraction import snippets as sn
from extraction.snippets import (
    MAX_SNIPPETS,
    _iter_tagged_fences,
    _spread_pick,
    extract_snippets,
    parse_snippet_budgets,
    snippet_budget_for,
)
from extraction.tree_helpers import get_parser

_CHECKS_DIR = Path(__file__).resolve().parents[3] / "ci" / "checks"
if str(_CHECKS_DIR) not in sys.path:
    sys.path.insert(0, str(_CHECKS_DIR))
import check_platform_capabilities as cpc  # noqa: E402

REAL_YAML = Path(__file__).resolve().parents[2] / "config" / "platform_capabilities.yaml"
TS_FIXTURE = Path(__file__).resolve().parents[1] / "fixtures" / "ts_flat_package"

# head = MAX - tier0 - reserve candidates are retained; see the fixtures below.
B3_BUDGET = {"docs_fence_budget": 5, "test_tail_reserve": 10, "stable_superset": True}


@pytest.fixture(autouse=True)
def _reset_snippet_config():
    sn.configure()
    yield
    sn.configure()


# ---------------------------------------------------------------------------
# Language-parametrized fixture builders (java + python)
# ---------------------------------------------------------------------------

class _Lang:
    def __init__(self, language, ext, fence_tags, fence_code_a, fence_code_b):
        self.language = language
        self.ext = ext
        self.fence_tags = fence_tags
        self.fence_code_a = fence_code_a
        self.fence_code_b = fence_code_b

    def test_file(self, name: str, prefix: str, n: int) -> str:
        raise NotImplementedError


class _JavaLang(_Lang):
    def test_file(self, name, prefix, n):
        methods = "\n".join(
            f"    public void test{prefix}{j}() {{ Object o = new Object(); }}"
            for j in range(n))
        return f"package demo;\npublic class {name}Test {{\n{methods}\n}}\n"


class _PythonLang(_Lang):
    def test_file(self, name, prefix, n):
        return "\n".join(
            f"def test_{prefix}_{j}():\n    x = {j}\n    assert x == {j}\n"
            for j in range(n))


JAVA = _JavaLang("java", ".java", ("java",),
                 "Pipeline p = new Pipeline();\np.run();\n",
                 "Gadget g = Gadget.open(\"a.bin\");\n")
PYTHON = _PythonLang("python", ".py", ("python", "py"),
                     "p = Pipeline()\np.run()\n",
                     "g = Gadget.open('a.bin')\n")
LANGS = [pytest.param(JAVA, id="java"), pytest.param(PYTHON, id="python")]


def _test_filename(lang: _Lang, name: str) -> str:
    return f"{name}Test{lang.ext}" if lang is JAVA else f"test_{name.lower()}{lang.ext}"


def _build_repo(root: Path, lang: _Lang, *, early_files: int, per_file: int,
                late_methods: int, reverse: bool = False) -> Path:
    """tests/e00..eNN each with `per_file` test functions, plus (optionally)
    tests/zz_new/ -- sorts AFTER every early file -- holding `late_methods`
    new-capability tests; README with two fenced blocks; docs/ with one
    language-tagged fence (new capability), an untagged fence, a foreign-
    language fence, and a duplicate of a README fence."""
    root.mkdir(parents=True, exist_ok=True)
    tag = lang.fence_tags[0]
    (root / "README.md").write_text(
        f"# Product\n\n```{tag}\n{lang.fence_code_a}```\n\n"
        f"```{tag}\n// second readme block\n{lang.fence_code_a}x = 1\n```\n",
        encoding="utf-8")
    docs = root / "docs" / "guide"
    docs.mkdir(parents=True)
    foreign = "ruby" if tag != "ruby" else "perl"
    (docs / "new_capability.md").write_text(
        f"# New capability\n\n```{tag}\n{lang.fence_code_b}```\n\n"
        f"```\nuntagged fence must be ignored\n```\n\n"
        f"```{foreign}\nputs 1\n```\n\n"
        f"~~~{tag}\n// tilde fence\n{lang.fence_code_b}y = 2\n~~~\n\n"
        f"```{tag}\n{lang.fence_code_a}```\n",  # duplicate of README block 1
        encoding="utf-8")
    specs = [(f"e{i:02d}", f"E{i:02d}", f"E{i:02d}", per_file) for i in range(early_files)]
    if late_methods:
        specs.append(("zz_new", "NewFeature", "NF", late_methods))
    if reverse:
        specs = list(reversed(specs))
    for dirname, name, prefix, n in specs:
        d = root / "tests" / dirname
        d.mkdir(parents=True, exist_ok=True)
        (d / _test_filename(lang, name)).write_text(
            lang.test_file(name, prefix, n), encoding="utf-8")
    return root


def _run(lang: _Lang, repo: Path, budget: "dict | None") -> list[dict]:
    sn.configure(budget_by_language={lang.language: budget} if budget else {})
    return extract_snippets(get_parser(lang.language), lang.language, repo, repo,
                            classes=[], formats=[])


def _ident(s: dict):
    return (s["source_file"], s["source_function"], s["source_line"])


def _code_ids(snips: list[dict]) -> list:
    return [_ident(s) for s in snips
            if s["source_function"] not in ("(readme_block)", "(docs_block)")]


# ---------------------------------------------------------------------------
# Config: the YAML is the source
# ---------------------------------------------------------------------------

class TestSnippetBudgetConfig:
    def test_parse_defaults_language_to_row_language_and_skips_legacy(self):
        caps = {"platforms": {
            "alpha": {"language": "lang_a",
                      "snippet_budget": {"mode": "tiered", "docs_fence_budget": 3}},
            "beta": {"language": "lang_b", "snippet_budget": {"mode": "legacy"}},
            "gamma": {"language": "lang_c"},  # absent == legacy
        }}
        assert parse_snippet_budgets(caps) == {
            "lang_a": {"docs_fence_budget": 3, "test_tail_reserve": 0,
                       "stable_superset": False}}

    def test_languages_list_fans_one_row_out_to_several_languages(self):
        caps = {"platforms": {"ts": {"language": "typescript", "snippet_budget": {
            "mode": "tiered", "languages": ["typescript", "javascript"]}}}}
        assert set(parse_snippet_budgets(caps)) == {"typescript", "javascript"}

    def test_real_yaml_declares_java_python_unchanged_and_ts_js_inert(self):
        sn.configure()  # real YAML
        assert snippet_budget_for("java")["docs_fence_budget"] > 0
        assert snippet_budget_for("java")["test_tail_reserve"] > 0
        assert snippet_budget_for("java")["stable_superset"] is True
        assert snippet_budget_for("python") is None
        assert snippet_budget_for("csharp") is None
        for lang in ("typescript", "javascript"):
            assert snippet_budget_for(lang) == {
                "docs_fence_budget": 0, "test_tail_reserve": 0,
                "stable_superset": False}

    def test_configure_capabilities_path_redirects_the_yaml_read(self, tmp_path):
        alt = tmp_path / "caps.yaml"
        alt.write_text(yaml.safe_dump({"platforms": {"x": {
            "language": "zz", "snippet_budget": {"mode": "tiered"}}}}),
            encoding="utf-8")
        sn.configure(capabilities_path=alt)
        assert snippet_budget_for("zz") is not None
        assert snippet_budget_for("java") is None

    def test_missing_yaml_fails_loud_naming_the_file_and_the_fix(self, tmp_path):
        missing = tmp_path / "nope.yaml"
        sn.configure(capabilities_path=missing)
        with pytest.raises(sn.SnippetBudgetConfigError) as exc:
            snippet_budget_for("java")
        msg = str(exc.value)
        assert str(missing) in msg and "platform_capabilities.yaml" in msg
        assert "restore" in msg or "configure(" in msg      # says how to fix it

    def test_invalid_yaml_syntax_names_the_file_and_the_fix(self, tmp_path):
        bad = tmp_path / "caps.yaml"
        bad.write_text("platforms: [unclosed\n", encoding="utf-8")
        sn.configure(capabilities_path=bad)
        with pytest.raises(sn.SnippetBudgetConfigError) as exc:
            snippet_budget_for("python")
        assert str(bad) in str(exc.value) and "Fix" in str(exc.value)

    def test_corrupt_block_of_another_platform_does_not_break_a_legacy_language(self, tmp_path):
        alt = tmp_path / "caps.yaml"
        alt.write_text(yaml.safe_dump({"platforms": {
            "alpha": {"language": "lang_a",
                      "snippet_budget": {"mode": "tiered", "docs_fence_budget": "not-an-int"}},
            "beta": {"language": "lang_b", "snippet_budget": {"mode": "legacy"}},
            "gamma": {"language": "lang_c", "snippet_budget": {"mode": "tiered", "languages": 5}},
            "delta": {"language": "lang_d", "snippet_budget": {"mode": "tiered"}},
        }}), encoding="utf-8")
        sn.configure(capabilities_path=alt)
        assert snippet_budget_for("lang_b") is None          # legacy: no dependence on alpha
        assert snippet_budget_for("lang_d") == {
            "docs_fence_budget": 0, "test_tail_reserve": 0, "stable_superset": False}
        with pytest.raises(sn.SnippetBudgetConfigError) as exc:
            snippet_budget_for("lang_a")                      # the corrupt row's OWN language
        assert "alpha" in str(exc.value) and "docs_fence_budget" in str(exc.value)
        with pytest.raises(sn.SnippetBudgetConfigError):      # strict parse still rejects it
            parse_snippet_budgets(yaml.safe_load(alt.read_text(encoding="utf-8")))


# ---------------------------------------------------------------------------
# Pure helpers
# ---------------------------------------------------------------------------

class TestFenceParsing:
    @pytest.mark.parametrize("tags", [("java",), ("python", "py")])
    def test_only_closed_language_tagged_fences_in_document_order(self, tags):
        t = tags[0]
        text = (
            f"```{t}\nA\n```\n"
            "```\nuntagged\n```\n"
            "```ruby\nforeign\n```\n"
            f"~~~{t}\nB\n~~~\n"
            f"```{{.{t}}}\nC\n```\n"
            f"```{t}\nunterminated\n")
        got = [(line, code) for line, code in _iter_tagged_fences(text, set(tags))]
        assert [c for _l, c in got] == ["A\n", "B\n", "C\n"]
        assert [l for l, _c in got] == sorted(l for l, _c in got)

    def test_longer_fence_markers_only_close_on_equal_or_longer(self):
        text = "````rust\n```\ninner\n```\n````\n"
        got = list(_iter_tagged_fences(text, {"rust"}))
        assert [c for _l, c in got] == ["```\ninner\n```\n"]


class TestSpreadPick:
    def test_returns_everything_when_k_covers_all(self):
        assert _spread_pick([1, 2, 3], 3) == [1, 2, 3]
        assert _spread_pick([1, 2, 3], 9) == [1, 2, 3]

    def test_zero_or_negative_k_picks_nothing(self):
        assert _spread_pick([1, 2, 3], 0) == []

    def test_spread_is_even_ordered_and_reaches_the_tail(self):
        items = list(range(100))
        picks = _spread_pick(items, 10)
        assert picks == sorted(picks) and len(set(picks)) == 10
        assert picks[0] < 10 and picks[-1] >= 90  # segment midpoints
        assert _spread_pick(items, 10) == picks    # pure


# ---------------------------------------------------------------------------
# Stable-superset selection (the core B3 contract)
# ---------------------------------------------------------------------------

@pytest.mark.parametrize("lang", LANGS)
class TestStableSupersetSelection:
    def _forced(self, tmp_path, lang, **kw):
        # 13 early files * 8 = 104 tests already exceed the 100-cap; the
        # late zz_new file (8 more) sorts after every one of them.
        return _build_repo(tmp_path / "repo", lang, early_files=13, per_file=8,
                           late_methods=8, **kw)

    def test_fixture_really_saturates_the_cap_before_the_late_tests(self, tmp_path, lang):
        repo = self._forced(tmp_path, lang)
        old = _run(lang, repo, None)
        assert len(old) == MAX_SNIPPETS
        assert not any("zz_new" in s["source_file"] for s in old)

    def test_new_capability_fences_and_tests_are_included(self, tmp_path, lang):
        repo = self._forced(tmp_path, lang)
        old = _run(lang, repo, None)
        new = _run(lang, repo, B3_BUDGET)
        assert len(new) <= MAX_SNIPPETS
        # README fences first, then docs fences, then code.
        kinds = [s["source_function"] for s in new]
        n_readme = kinds.count("(readme_block)")
        n_docs = kinds.count("(docs_block)")
        assert n_readme == 2 and n_docs >= 2
        assert kinds[:n_readme] == ["(readme_block)"] * n_readme
        assert kinds[n_readme:n_readme + n_docs] == ["(docs_block)"] * n_docs
        docs = [s for s in new if s["source_function"] == "(docs_block)"]
        assert all(s["source_file"] == "docs/guide/new_capability.md" for s in docs)
        assert any(lang.fence_code_b.strip() in s["code"] for s in docs)
        # untagged / foreign / README-duplicate fences never harvested
        assert not any("untagged" in s["code"] or "puts 1" in s["code"] for s in docs)
        assert sum(lang.fence_code_a.strip() in s["code"] for s in docs) == 0
        # new-feature tests (sort after the old cut) now present, absent before
        late = [s for s in new if "zz_new" in s["source_file"]]
        assert len(late) >= 3
        assert not any("zz_new" in s["source_file"] for s in old)

    def test_old_selection_is_a_retained_prefix_and_eviction_is_the_tail(self, tmp_path, lang):
        repo = self._forced(tmp_path, lang)
        old = _run(lang, repo, None)
        new = _run(lang, repo, B3_BUDGET)
        tier0 = sum(1 for s in new if s["source_function"] in ("(readme_block)", "(docs_block)"))
        test_budget = MAX_SNIPPETS - tier0
        head_len = test_budget - B3_BUDGET["test_tail_reserve"]
        old_ids, new_ids = _code_ids(old), _code_ids(new)
        # documented rule: the first (budget - R) old snippets survive, in order
        assert new_ids[:head_len] == old_ids[:head_len]
        # ... and ONLY old snippets beyond that prefix may be evicted.
        evicted = set(old_ids) - set(new_ids)
        assert evicted <= set(old_ids[head_len:])
        # everything new beyond the prefix is a tail pick from the remainder
        assert set(new_ids[head_len:]) <= set(_code_ids(_run_all_candidates(lang, repo))[head_len:])

    def test_under_cap_nothing_is_evicted_strict_superset(self, tmp_path, lang):
        repo = _build_repo(tmp_path / "small", lang, early_files=3, per_file=4,
                           late_methods=4)
        old = _run(lang, repo, None)
        new = _run(lang, repo, B3_BUDGET)
        assert len(old) < MAX_SNIPPETS
        assert set(_code_ids(old)) <= set(_code_ids(new))
        assert _code_ids(old) == _code_ids(new)  # same order too
        assert any(s["source_function"] == "(docs_block)" for s in new)

    def test_output_is_deterministic_and_independent_of_creation_order(self, tmp_path, lang):
        a = self._forced(tmp_path / "a", lang)
        b = self._forced(tmp_path / "b", lang, reverse=True)
        first = _run(lang, a, B3_BUDGET)
        assert first == _run(lang, a, B3_BUDGET)
        assert first == _run(lang, b, B3_BUDGET)

    def test_independent_of_prior_knowledge_bundle_state(self, tmp_path, lang):
        a = self._forced(tmp_path / "a", lang)
        b = self._forced(tmp_path / "b", lang)
        stale = b / "knowledge" / "merged"
        stale.mkdir(parents=True)
        (stale / "model.yaml").write_text("snippets: [bogus]\n", encoding="utf-8")
        (b / "runs").mkdir()
        (b / "runs" / "prior_snippets.json").write_text("[]", encoding="utf-8")
        assert _run(lang, a, B3_BUDGET) == _run(lang, b, B3_BUDGET)

    def test_snippet_ids_contiguous_and_keys_unique(self, tmp_path, lang):
        repo = self._forced(tmp_path, lang)
        new = _run(lang, repo, B3_BUDGET)
        assert [s["id"] for s in new] == [f"snippet_{i:03d}" for i in range(1, len(new) + 1)]
        assert len({s["snippet_key"] for s in new}) == len(new)


def _run_all_candidates(lang: _Lang, repo: Path) -> list[dict]:
    """Every tier-2 candidate in discovery order (no cap): a tiered run with a
    huge docs budget off and the cap bypassed via the collector directly."""
    from extraction.snippets import (
        _TIER2_TEST_DIR_NAMES, _collect_tier_candidates,
        _discover_snippet_dir_files, _search_base_list)
    from extraction.tree_helpers import _CLASS_TYPES, _FILE_EXTENSIONS, _FUNC_TYPES
    files = _discover_snippet_dir_files(
        _TIER2_TEST_DIR_NAMES, _search_base_list(repo, repo), repo,
        _FILE_EXTENSIONS[lang.language], repo.name, is_example_dir=False)
    return _collect_tier_candidates(
        files, get_parser(lang.language), lang.language,
        _FUNC_TYPES[lang.language], _CLASS_TYPES[lang.language], repo,
        set(), {}, set(), preserve_discovery_order=True)


# ---------------------------------------------------------------------------
# Golden parity: not opted in / inert knobs => untouched behaviour
# ---------------------------------------------------------------------------

class TestNonOptedInParity:
    def test_python_not_opted_in_ignores_docs_and_tail_reserve(self, tmp_path):
        repo = tmp_path / "pyrepo"
        (repo / "tests").mkdir(parents=True)
        (repo / "docs").mkdir()
        (repo / "tests" / "test_a.py").write_text(
            "def test_a1():\n    x = 1\n\ndef test_a2():\n    x = 2\n", encoding="utf-8")
        (repo / "tests" / "test_b.py").write_text(
            "def test_b1():\n    y = 1\n", encoding="utf-8")
        (repo / "README.md").write_text("```python\nr = 1\n```\n", encoding="utf-8")
        (repo / "docs" / "g.md").write_text("```python\nd = 1\n```\n", encoding="utf-8")
        expected = [
            ("tests/test_a.py", "test_a1"), ("tests/test_a.py", "test_a2"),
            ("tests/test_b.py", "test_b1"), ("README.md", "(readme_block)")]

        sn.configure()  # real YAML: python is legacy
        real = extract_snippets(get_parser("python"), "python", repo, repo, [], [])
        assert [(s["source_file"], s["source_function"]) for s in real] == expected
        assert all("snippet_key" not in s for s in real)

        # a budget declared for ANOTHER language never leaks into python
        sn.configure(budget_by_language={"java": B3_BUDGET})
        other = extract_snippets(get_parser("python"), "python", repo, repo, [], [])
        assert other == real

    def test_csharp_not_opted_in_golden_on_synthetic_tree(self, tmp_path):
        repo = tmp_path / "cs"
        (repo / "Prod.Tests").mkdir(parents=True)
        (repo / "docs").mkdir()
        (repo / "Prod.Tests" / "AThing.cs").write_text(
            "namespace P { public class AThingTests { public void TestOne() { var x = 1; } } }\n",
            encoding="utf-8")
        (repo / "docs" / "g.md").write_text("```csharp\nvar d = 1;\n```\n", encoding="utf-8")
        pkg = repo / "Prod"
        pkg.mkdir()
        sn.configure()
        out = extract_snippets(get_parser("csharp"), "csharp", pkg, repo, [], [])
        assert [(s["source_file"], s["source_function"]) for s in out] == [
            ("Prod.Tests/AThing.cs", "TestOne")]

    def test_typescript_with_inert_knobs_ignores_docs_fences(self, tmp_path):
        with_docs = tmp_path / "with_docs"
        without = tmp_path / "without"
        shutil.copytree(TS_FIXTURE, with_docs)
        shutil.copytree(TS_FIXTURE, without)
        (with_docs / "docs").mkdir(exist_ok=True)
        (with_docs / "docs" / "zz_b3_extra.md").write_text(
            "```ts\nexport const docOnly = 1;\n```\n", encoding="utf-8")
        sn.configure()  # real YAML: typescript tiered, knobs all off
        a = extract_snippets(get_parser("typescript"), "typescript", with_docs, with_docs, [], [])
        b = extract_snippets(get_parser("typescript"), "typescript", without, without, [], [])
        norm = lambda L: [{k: v for k, v in s.items()} for s in L]  # noqa: E731
        assert norm(a) == norm(b)
        assert not any(s["source_function"] == "(docs_block)" for s in a)
        assert all("snippet_key" in s for s in a)  # tiered shape unchanged

    def test_tiered_with_zero_knobs_equals_pre_b3_global_path_sort(self, tmp_path):
        """Python opted in with all knobs zero must keep the original tiered
        contract: README, then tests sorted globally by (path, line)."""
        repo = _build_repo(tmp_path / "r", PYTHON, early_files=2, per_file=2,
                           late_methods=2)
        zero = {"docs_fence_budget": 0, "test_tail_reserve": 0, "stable_superset": False}
        out = _run(PYTHON, repo, zero)
        assert not any(s["source_function"] == "(docs_block)" for s in out)
        code = _code_ids(out)
        assert code == sorted(code, key=lambda t: (t[0].lower(), t[2]))


# ---------------------------------------------------------------------------
# CI check: check_snippet_budget
# ---------------------------------------------------------------------------

def _real_caps() -> dict:
    with open(REAL_YAML, encoding="utf-8") as f:
        return yaml.safe_load(f)


class TestCheckSnippetBudget:
    def _check(self, caps):
        sn.configure()
        return cpc.check_snippet_budget(caps, sorted(caps["platforms"]))

    def test_real_yaml_has_no_findings(self):
        assert self._check(_real_caps()) == []

    def test_missing_block_is_a_finding(self):
        caps = _real_caps()
        del caps["platforms"]["python"]["snippet_budget"]
        assert any("no snippet_budget block" in f["detail"] for f in self._check(caps))

    def test_unknown_mode_is_a_finding(self):
        caps = _real_caps()
        caps["platforms"]["java"]["snippet_budget"]["mode"] = "bogus"
        assert any("not in" in f["detail"] for f in self._check(caps))

    def test_double_claimed_language_is_a_finding(self):
        caps = _real_caps()
        caps["platforms"]["java"]["snippet_budget"]["languages"] = ["java", "typescript"]
        assert any("already claimed" in f["detail"] or "disagree" in f["detail"]
                   or "loads" in f["detail"] for f in self._check(caps))

    def test_knob_out_of_range_is_a_finding(self):
        caps = _real_caps()
        caps["platforms"]["java"]["snippet_budget"]["docs_fence_budget"] = MAX_SNIPPETS + 1
        assert any("docs_fence_budget" in f["detail"] for f in self._check(caps))

    def test_yaml_vs_loader_disagreement_fails_closed(self):
        """Declare python tiered in the YAML under test while the loader (live
        YAML) still treats it as legacy -> the agreement check fires."""
        caps = copy.deepcopy(_real_caps())
        caps["platforms"]["python"]["snippet_budget"] = {"mode": "tiered"}
        assert any("python" in f["detail"] and "loads" in f["detail"]
                   for f in self._check(caps))

    def test_legacy_declared_but_loaded_tiered_fails_closed(self):
        caps = _real_caps()
        sn.configure(budget_by_language={"python": {
            "docs_fence_budget": 0, "test_tail_reserve": 0, "stable_superset": False}})
        findings = cpc.check_snippet_budget(caps, sorted(caps["platforms"]))
        assert any("declares mode legacy" in f["detail"] for f in findings)


# ---------------------------------------------------------------------------
# R3-6: pin exactly what `stable_superset` guarantees
# ---------------------------------------------------------------------------

class TestStableSupersetFlagIsPinned:
    """`tests/` AND `test/` both exist. Legacy order visits tests/ first
    (60 snippets) then test/ (first 40 of 60). A global (path, line) sort
    puts `test/...` BEFORE `tests/...`, so with the flag OFF the head of the
    new selection is mostly test/ and the legacy tests/ prefix is displaced.
    With the flag ON the legacy discovery order is kept and the first
    (tier-2 budget - test_tail_reserve) legacy snippets are retained.
    A mutant that ignores the flag (preserve_discovery_order) makes ON == OFF
    and fails the margin assertion below."""

    def _tree(self, root: Path) -> Path:
        for dirname in ("tests", "test"):
            for f in range(6):
                d = root / dirname
                d.mkdir(parents=True, exist_ok=True)
                body = "\n".join(
                    f"def test_{dirname}_{f}_{j}():\n    x = {j}\n" for j in range(10))
                (d / f"test_{f:02d}.py").write_text(body, encoding="utf-8")
        return root

    def test_flag_on_retains_the_legacy_prefix_flag_off_displaces_it(self, tmp_path):
        repo = self._tree(tmp_path / "r")
        old = _code_ids(_run(PYTHON, repo, None))
        assert len(old) == MAX_SNIPPETS
        assert old[0][0].startswith("tests/") and old[-1][0].startswith("test/")
        knobs = {"docs_fence_budget": 0, "test_tail_reserve": 10}
        on = _code_ids(_run(PYTHON, repo, {**knobs, "stable_superset": True}))
        off = _code_ids(_run(PYTHON, repo, {**knobs, "stable_superset": False}))
        head = MAX_SNIPPETS - knobs["test_tail_reserve"]
        retained = lambda new: len(set(old) & set(new))  # noqa: E731
        # GUARANTEE (ON): the first (budget - reserve) legacy snippets, in order.
        assert on[:head] == old[:head]
        assert retained(on) >= head
        # FLAG OFF displaces that prefix (global path sort: test/ before tests/).
        assert off[:head] != old[:head]
        assert retained(off) <= retained(on) - 8
        # Tail picks are the only non-prefix members; none duplicate the head.
        assert len(set(on)) == len(on) == MAX_SNIPPETS

    def test_flag_has_no_effect_when_everything_fits(self, tmp_path):
        repo = tmp_path / "small"
        (repo / "tests").mkdir(parents=True)
        (repo / "test").mkdir()
        (repo / "tests" / "test_a.py").write_text("def test_a():\n    x = 1\n", encoding="utf-8")
        (repo / "test" / "test_b.py").write_text("def test_b():\n    x = 1\n", encoding="utf-8")
        knobs = {"docs_fence_budget": 0, "test_tail_reserve": 10}
        on = _code_ids(_run(PYTHON, repo, {**knobs, "stable_superset": True}))
        off = _code_ids(_run(PYTHON, repo, {**knobs, "stable_superset": False}))
        # The SET is a superset of the legacy one either way; only ORDER differs.
        old = _code_ids(_run(PYTHON, repo, None))
        assert set(old) <= set(on) and set(old) <= set(off)
        assert on == old and off != old
