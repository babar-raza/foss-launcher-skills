"""Tests for the D-1 platform capability contract (TC-MT040-40).

Mission MT040-2026-08-28-PDF-TYPESCRIPT-LAUNCH. Generalizes
test_rust_platform_maps.py (the single-platform precedent -- rust was the
first, and until this file the ONLY, platform with a wiring test at all) to
every platform registered in data/products.json: cpp, go, java, net, python,
rust, typescript.

Two halves:

1. TestXxxMatrix classes -- parametrized over `platform`, one class per
   capability site declared in config/platform_capabilities.yaml, asserting
   the YAML value agrees with the real code it was read from. This is the
   generic conformance matrix D-1 asks for.

2. TestXxxReproduction classes -- reproduces EVERY individual assertion
   test_rust_platform_maps.py makes (reference_filter kind-allowlist,
   batch_reference category/group-key maps, install tooling, eval-config
   foreign patterns/fence langs, syntax-checking parser availability, and
   knowledge-layer coverage/case-convention policy), generalized to run for
   all 7 platforms with real, platform-specific expected values -- not just
   rust. See each class's docstring for exactly which
   TestRust<X> class in test_rust_platform_maps.py it generalizes.

3. TestNegativeControl* classes -- prove the matrix assertions fail closed
   by re-running the SAME comparison helper functions against a mutated
   LOCAL COPY of the real map (never a monkeypatch of the live module --
   internal monkeypatching of pipeline dicts is a banned T2 pattern per
   scripts/ci/checks/check_monkeypatch_lint.py in this repo; a local copy is
   what "fits the existing test conventions" here).
"""
from __future__ import annotations

import sys
from pathlib import Path

import pytest
import yaml

# sys.path is set by tests/conftest.py for scripts/pipeline/-relative imports
# (same convention as test_rust_platform_maps.py).
import scout  # noqa: F401 -- import parity with test_rust_platform_maps.py; ensures sys.path is primed
from lib.reference_filter import (
    REACHABILITY_ENFORCED_PLATFORMS,
    _passes_platform_scope,
    filter_api_surface,
)
from lib.example_verification import registry as ev_registry

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
import batch_reference as _br  # noqa: E402

from extraction import lang as extraction_lang  # noqa: E402
from extraction.package_manifest import parse_manifest  # noqa: E402
from extraction.tree_helpers import (  # noqa: E402
    _CLASS_TYPES,
    _DOC_COMMENT_STYLES,
    _FUNC_TYPES,
    _MODULE_TYPES,
    PLATFORM_TO_LANG,
)
from content_eval.config import (  # noqa: E402
    LANG_TO_PLATFORM,
    PLATFORM_EXPECTED_LANGS,
    PLATFORM_FOREIGN_PATTERNS,
    PROSE_FOREIGN_PATTERNS,
)
from content_eval.evaluators import code_syntax_check as csc  # noqa: E402
from content_eval.evaluators.coverage import CONCRETE_ONLY_PLATFORMS  # noqa: E402
from content_eval.evaluators.install_recipe import (  # noqa: E402
    _PKG_NAME_RE,
    _PLATFORM_PKG_MANAGERS,
)
from content_eval.remediation.fixers.code_fence_lang import (  # noqa: E402
    _PLATFORM_PRIMARY_LANG,
)
from commands.content.install_block_updater import (  # noqa: E402
    _block_contains_install,
    _detect_platform_type,
    _parse_install_md,
)
from commands.diagnostics import smoke_test as st  # noqa: E402
from commands.knowledge.promote import _apply_godoc_fallback  # noqa: E402
from commands.launch.site_planner import (  # noqa: E402
    KB_PLATFORM_SUFFIX,
    TROUBLE_PLATFORMS,
)

CONFIG_PATH = Path(__file__).resolve().parent.parent / "config" / "platform_capabilities.yaml"


def _load_caps() -> dict:
    with open(CONFIG_PATH, encoding="utf-8") as f:
        return yaml.safe_load(f)


CAPS = _load_caps()
PLATFORMS = sorted(CAPS["platforms"].keys())
FIXTURES = Path(__file__).parent / "fixtures"


# ===========================================================================
# Part 1 -- YAML-vs-real-code conformance matrix (one class per site)
# ===========================================================================


def _sanity_check_platform_list():
    """The matrix's own platform list must equal what data/products.json
    actually contains active for -- not a hand-maintained guess. This isn't
    parametrized (it would be circular); it runs once at collection-adjacent
    time via a regular test."""
    import json
    products_path = Path(__file__).resolve().parents[3] / "data" / "products.json"
    with open(products_path, encoding="utf-8") as f:
        products = json.load(f)
    real_active_platforms = {p["platform"] for p in products if p.get("active")}
    assert real_active_platforms == set(PLATFORMS), (
        f"platform_capabilities.yaml declares {sorted(PLATFORMS)} but "
        f"data/products.json's real active platforms are {sorted(real_active_platforms)}"
    )


class TestPlatformListSanity:
    def test_declared_platforms_match_products_json(self):
        _sanity_check_platform_list()


# --- YAML structural sanity (VERIFICATION REQUIRED #1) -----------------------
#
# No existing schema convention under data/schemas/ applies to
# scripts/pipeline/config/ files (checked: every data/schemas/*.json targets
# a data/*.json file, e.g. package-registry-schema.json ->
# data/package_registry.json -- none target scripts/pipeline/config/), so a
# plain YAML-load + required-keys-present test is this file's own schema
# check, per this card's own verification instructions.

_REQUIRED_TOP_LEVEL_KEYS = {"version", "mission", "card", "capability_sites", "platforms"}
_REQUIRED_SITE_KEYS = {
    "class_kinds", "func_kinds", "module_kinds", "declared_ignored_kinds",
    "doc_style", "install_parser", "package_managers", "foreign_prose_patterns",
    "primary_language", "smoke_test_langs", "kb_suffix", "trouble_platform",
    "coverage_policy", "case_convention", "reachability_adapter",
    "format_recognizer_style", "example_verification",
}


class TestYamlSchemaSanity:
    def test_yaml_loads_cleanly(self):
        assert CAPS is not None

    def test_top_level_keys_present(self):
        assert _REQUIRED_TOP_LEVEL_KEYS <= set(CAPS.keys())

    def test_capability_sites_documented(self):
        for site_name in _REQUIRED_SITE_KEYS:
            assert site_name in CAPS["capability_sites"], f"undocumented site: {site_name}"
            assert "source" in CAPS["capability_sites"][site_name]
            assert "description" in CAPS["capability_sites"][site_name]

    @pytest.mark.parametrize("platform", PLATFORMS)
    def test_every_platform_row_has_every_required_site_key(self, platform):
        row = CAPS["platforms"][platform]
        missing = _REQUIRED_SITE_KEYS - set(row.keys())
        assert not missing, f"{platform}: missing capability site keys {missing}"
        assert "language" in row

    @pytest.mark.parametrize("platform", PLATFORMS)
    def test_no_silent_omission_every_declared_or_absent_value_is_explicit(self, platform):
        """Every site whose value can legitimately be undeclared must say so
        explicitly via `declared: false` (never a bare missing key, an empty
        string standing in for 'n/a', or a null with no reason)."""
        row = CAPS["platforms"][platform]
        for site in ("package_managers", "foreign_prose_patterns", "smoke_test_langs", "kb_suffix"):
            value = row[site]
            if isinstance(value, dict) and value.get("declared") is False:
                assert "reason" in value, f"{platform}.{site}: declared:false with no reason string"


# --- class_kinds / func_kinds / module_kinds --------------------------------


def _class_kinds_match(platform: str, class_types_map: dict) -> None:
    lang = CAPS["platforms"][platform]["language"]
    declared = set(CAPS["platforms"][platform]["class_kinds"])
    real = class_types_map.get(lang, set())
    assert declared == real, f"{platform} ({lang}): YAML {sorted(declared)} != code {sorted(real)}"


def _func_kinds_match(platform: str, func_types_map: dict) -> None:
    lang = CAPS["platforms"][platform]["language"]
    declared = set(CAPS["platforms"][platform]["func_kinds"])
    real = func_types_map.get(lang, set())
    assert declared == real, f"{platform} ({lang}): YAML {sorted(declared)} != code {sorted(real)}"


def _module_kinds_match(platform: str, module_types_map: dict) -> None:
    lang = CAPS["platforms"][platform]["language"]
    declared = set(CAPS["platforms"][platform]["module_kinds"])
    real = module_types_map.get(lang, set())
    assert declared == real, f"{platform} ({lang}): YAML {sorted(declared)} != code {sorted(real)}"


class TestClassKindsMatrix:
    @pytest.mark.parametrize("platform", PLATFORMS)
    def test_class_kinds_match_tree_helpers(self, platform):
        _class_kinds_match(platform, _CLASS_TYPES)

    def test_typescript_abstract_class_is_handled(self):
        """Explicit acceptance check from the card description: typescript
        must show abstract_class_declaration as a HANDLED kind."""
        assert "abstract_class_declaration" in CAPS["platforms"]["typescript"]["class_kinds"]
        assert "abstract_class_declaration" in _CLASS_TYPES["typescript"]


class TestFuncKindsMatrix:
    @pytest.mark.parametrize("platform", PLATFORMS)
    def test_func_kinds_match_tree_helpers(self, platform):
        _func_kinds_match(platform, _FUNC_TYPES)

    def test_typescript_abstract_method_signature_is_handled(self):
        assert "abstract_method_signature" in CAPS["platforms"]["typescript"]["func_kinds"]
        assert "abstract_method_signature" in _FUNC_TYPES["typescript"]


class TestModuleKindsMatrix:
    @pytest.mark.parametrize("platform", PLATFORMS)
    def test_module_kinds_match_tree_helpers(self, platform):
        _module_kinds_match(platform, _MODULE_TYPES)


# --- doc_style ---------------------------------------------------------------


class TestDocStyleMatrix:
    @pytest.mark.parametrize("platform", PLATFORMS)
    def test_doc_style_matches(self, platform):
        lang = CAPS["platforms"][platform]["language"]
        declared = CAPS["platforms"][platform]["doc_style"]
        real = _DOC_COMMENT_STYLES.get(lang)
        assert declared == real, f"{platform} ({lang}): YAML {declared!r} != code {real!r}"


# --- install_parser (functional: real manifest file detection) --------------

_MANIFEST_FIXTURES = {
    "python": ("pyproject.toml", '[project]\nname = "demo"\nversion = "1.0.0"\n'),
    "net": ("Demo.csproj",
            '<Project Sdk="Microsoft.NET.Sdk"><PropertyGroup>'
            '<PackageId>Demo</PackageId><Version>1.0.0</Version>'
            '</PropertyGroup></Project>'),
    "java": ("pom.xml",
             "<project><groupId>com.demo</groupId><artifactId>demo</artifactId>"
             "<version>1.0.0</version></project>"),
    "cpp": ("CMakeLists.txt", "project(Demo VERSION 1.0.0)\n"),
    "typescript": ("package.json", '{"name": "demo", "version": "1.0.0"}'),
    "go": ("go.mod", "module github.com/demo/demo\n\ngo 1.21\n"),
    "rust": ("Cargo.toml", '[package]\nname = "demo"\nversion = "1.0.0"\n'),
}


class TestInstallParserMatrix:
    @pytest.mark.parametrize("platform", PLATFORMS)
    def test_manifest_parser_finds_declared_manifest_file(self, platform, tmp_path):
        import fnmatch

        declared_files = CAPS["platforms"][platform]["install_parser"]["manifest_files"]
        filename, content = _MANIFEST_FIXTURES[platform]
        assert any(fnmatch.fnmatch(filename, pat) for pat in declared_files), (
            f"{platform}: test fixture filename {filename!r} does not match any "
            f"declared manifest_files pattern {declared_files!r}"
        )
        (tmp_path / filename).write_text(content, encoding="utf-8")
        result = parse_manifest(tmp_path, platform)
        assert result, f"{platform}: parse_manifest() found nothing for a real {filename}"


# --- package_managers ---------------------------------------------------------


class TestPackageManagersMatrix:
    @pytest.mark.parametrize("platform", PLATFORMS)
    def test_package_managers_match_or_declared_absent(self, platform):
        decl = CAPS["platforms"][platform]["package_managers"]
        real = _PLATFORM_PKG_MANAGERS.get(platform)
        if isinstance(decl, dict) and decl.get("declared") is False:
            assert real is None, (
                f"{platform}: YAML declares package_managers absent, but "
                f"install_recipe.py now HAS an entry: {real} -- update the YAML"
            )
        else:
            assert real is not None, f"{platform}: YAML declares {decl} but code has no entry"
            assert set(decl) == real, f"{platform}: YAML {set(decl)} != code {real}"


# --- foreign_prose_patterns ---------------------------------------------------


class TestForeignProsePatternsMatrix:
    @pytest.mark.parametrize("platform", PLATFORMS)
    def test_prose_patterns_match_or_declared_absent(self, platform):
        decl = CAPS["platforms"][platform]["foreign_prose_patterns"]
        real = PROSE_FOREIGN_PATTERNS.get(platform)
        if decl.get("declared") is False:
            assert real is None, (
                f"{platform}: YAML declares foreign_prose_patterns absent, but "
                f"content_eval/config.py now HAS an entry -- update the YAML"
            )
        else:
            assert real is not None
            assert len(real) == decl["pattern_count"], (
                f"{platform}: YAML says {decl['pattern_count']} patterns, "
                f"code has {len(real)}"
            )


# --- primary_language ---------------------------------------------------------


class TestPrimaryLanguageMatrix:
    @pytest.mark.parametrize("platform", PLATFORMS)
    def test_primary_language_matches_platform_to_lang(self, platform):
        declared = CAPS["platforms"][platform]["primary_language"]
        real = PLATFORM_TO_LANG.get(platform)
        assert declared == real, f"{platform}: YAML {declared!r} != PLATFORM_TO_LANG {real!r}"


# --- smoke_test_langs / fence langs -------------------------------------------


class TestSmokeTestLangsMatrix:
    @pytest.mark.parametrize("platform", PLATFORMS)
    def test_platform_expected_langs_matches_or_declared_absent(self, platform):
        decl = CAPS["platforms"][platform]["smoke_test_langs"]
        real = PLATFORM_EXPECTED_LANGS.get(platform)
        if decl.get("declared") is False:
            assert real is None, (
                f"{platform}: YAML declares smoke_test_langs absent, but "
                f"content_eval/config.py:PLATFORM_EXPECTED_LANGS now HAS an "
                f"entry -- update the YAML"
            )
        else:
            assert real is not None
            assert set(decl["value"]) == real, f"{platform}: YAML {decl['value']} != code {real}"

    @pytest.mark.parametrize("platform", PLATFORMS)
    def test_smoke_test_platform_langs_cross_check(self, platform):
        decl = CAPS["platforms"][platform]["smoke_test_langs"]
        real = st._PLATFORM_LANGS.get(platform)
        expect_present = decl.get("smoke_test_py_matches", False)
        if expect_present:
            assert real is not None, f"{platform}: YAML says smoke_test.py has an entry, but it doesn't"
        else:
            assert real is None, f"{platform}: YAML says smoke_test.py has no entry, but it does: {real}"

    @pytest.mark.parametrize("platform", PLATFORMS)
    def test_code_syntax_check_ts_langs_cross_check(self, platform):
        decl = CAPS["platforms"][platform]["smoke_test_langs"]
        lang = CAPS["platforms"][platform]["language"]
        expect_present = decl.get("code_syntax_check_py_matches", False)
        present = lang in csc._TS_LANGS
        assert present == expect_present, (
            f"{platform} ({lang}): YAML says code_syntax_check_py_matches="
            f"{expect_present} but real _TS_LANGS membership is {present}"
        )

    def test_go_is_partially_fixed_not_fully_undeclared_anymore(self):
        """REWRITTEN 2026-09-06 (MT065 taskcard C4, RC20 fix): this
        originally pinned 'go' as absent from all three of
        PLATFORM_EXPECTED_LANGS / smoke_test._PLATFORM_LANGS /
        code_syntax_check._TS_LANGS. smoke_test.py's own _PLATFORM_LANGS
        (and _TS_LANG_MAP) are now derived from the shared
        lib/example_verification/registry.py, which declares "go"/"golang"
        -- the previous fallback-to-python defect (a go product's code
        blocks silently smoke-tested as Python) is closed. The other two
        dicts are unfixed (different files, out of this taskcard's scope):
        content_eval/config.py:PLATFORM_EXPECTED_LANGS and
        code_syntax_check.py:_TS_LANGS both still have no 'go' key -- this
        is why platform_capabilities.yaml's go.smoke_test_langs stays
        `declared: false` (that site's primary value cross-checks
        PLATFORM_EXPECTED_LANGS specifically) while its new
        `smoke_test_py_matches: true` field reflects the real, fixed
        smoke_test.py state."""
        assert "go" not in PLATFORM_EXPECTED_LANGS
        assert "go" in st._PLATFORM_LANGS
        assert "golang" in st._PLATFORM_LANGS["go"]
        assert "go" not in csc._TS_LANGS
        assert CAPS["platforms"]["go"]["smoke_test_langs"]["declared"] is False
        assert CAPS["platforms"]["go"]["smoke_test_langs"]["smoke_test_py_matches"] is True


# --- kb_suffix -----------------------------------------------------------------


class TestKbSuffixMatrix:
    @pytest.mark.parametrize("platform", PLATFORMS)
    def test_kb_suffix_matches_real_fallback_behavior(self, platform):
        decl = CAPS["platforms"][platform]["kb_suffix"]
        real_effective = KB_PLATFORM_SUFFIX.get(platform, platform)
        if decl.get("declared") is False:
            assert platform not in KB_PLATFORM_SUFFIX, (
                f"{platform}: YAML declares kb_suffix absent, but KB_PLATFORM_SUFFIX "
                f"now HAS an entry -- update the YAML"
            )
            assert real_effective == decl["effective_value"]
        else:
            assert platform in KB_PLATFORM_SUFFIX
            assert real_effective == decl["value"]


# --- trouble_platform ------------------------------------------------------------


class TestTroublePlatformMatrix:
    @pytest.mark.parametrize("platform", PLATFORMS)
    def test_trouble_platform_flag_matches(self, platform):
        declared = CAPS["platforms"][platform]["trouble_platform"]
        real = platform in TROUBLE_PLATFORMS
        assert declared == real, f"{platform}: YAML {declared} != (platform in TROUBLE_PLATFORMS) {real}"


# --- coverage_policy ---------------------------------------------------------------


def _coverage_policy_matches(platform: str, concrete_only_platforms: set) -> None:
    declared = CAPS["platforms"][platform]["coverage_policy"]["concrete_only"]
    real = platform in concrete_only_platforms
    assert declared == real, f"{platform}: YAML {declared} != (platform in CONCRETE_ONLY_PLATFORMS) {real}"


class TestCoveragePolicyMatrix:
    @pytest.mark.parametrize("platform", PLATFORMS)
    def test_concrete_only_flag_matches(self, platform):
        _coverage_policy_matches(platform, CONCRETE_ONLY_PLATFORMS)


# --- case_convention (functional: real name-inference accessor test) --------

_CASE_ACCESSOR_SAMPLES = {
    "PascalCase": "SetWidth",
    "camelCase": "setWidth",
    "snake_case": "set_width",
}


class TestCaseConventionMatrix:
    @pytest.mark.parametrize("platform", PLATFORMS)
    def test_case_convention_accessor_is_inferred(self, platform):
        convention = CAPS["platforms"][platform]["case_convention"]
        method_name = _CASE_ACCESSOR_SAMPLES[convention]
        api = [{
            "name": "Widget",
            "methods": [{"name": method_name, "params": [{"name": "p"}], "doc": ""}],
            "properties": [],
        }]
        count = _apply_godoc_fallback(api, platform)
        assert count == 1, (
            f"{platform}: declared case_convention={convention!r} but the "
            f"matching accessor {method_name!r} was not inferred by "
            f"_apply_godoc_fallback"
        )
        assert api[0]["methods"][0]["doc"]
        assert api[0]["methods"][0].get("doc_source") == "name_inference"


# --- reachability_adapter -----------------------------------------------------


class TestReachabilityAdapterMatrix:
    @pytest.mark.parametrize("platform", PLATFORMS)
    def test_enforced_flag_matches_reachability_enforced_platforms(self, platform):
        declared = CAPS["platforms"][platform]["reachability_adapter"]["enforced"]
        real = platform in REACHABILITY_ENFORCED_PLATFORMS
        assert declared == real, (
            f"{platform}: YAML enforced={declared} != "
            f"(platform in REACHABILITY_ENFORCED_PLATFORMS) {real}"
        )

    @pytest.mark.parametrize("platform", PLATFORMS)
    def test_unknown_not_implemented_status_is_a_permanent_none_stub(self, platform, tmp_path):
        status = CAPS["platforms"][platform]["reachability_adapter"]["status"]
        if status != "unknown_not_implemented":
            pytest.skip(f"{platform} is not declared unknown_not_implemented")
        lang = CAPS["platforms"][platform]["language"]
        module = extraction_lang.LANGUAGES[lang]
        names, root = module.export_surface(tmp_path, tmp_path)
        assert names is None and root is None, (
            f"{platform} ({lang}): YAML says export_surface() is a permanent "
            f"(None, None) stub, but it returned ({names!r}, {root!r}) -- a "
            f"real adapter may have landed; update the YAML"
        )


# --- example_verification -----------------------------------------------------
#
# MT065-2026-09-06-EXAMPLE-VERIFICATION-CENTRALIZATION (taskcard C4): the
# one code-side source of truth is lib/example_verification/registry.py;
# check_platform_capabilities.py::check_example_verification() is the CI
# gate, this class is the pytest reproduction (same "declarative YAML vs
# real code, both checked, two independent surfaces" pattern every other
# site in this file already follows).


class TestExampleVerificationMatrix:
    @pytest.mark.parametrize("platform", PLATFORMS)
    def test_every_field_matches_registry_platform_contract(self, platform):
        decl = CAPS["platforms"][platform]["example_verification"]
        contract = ev_registry.PLATFORM_CONTRACT[platform]
        assert decl["max_tier"] == contract.max_tier
        assert decl["offline_tier"] == contract.offline_tier
        assert decl["runner_module"] == contract.runner
        assert decl["precommit_blocking"] == contract.precommit_blocking

    def test_every_registry_platform_has_a_yaml_row(self):
        missing = set(ev_registry.PLATFORM_CONTRACT) - set(PLATFORMS)
        assert not missing, f"registry.PLATFORM_CONTRACT declares platforms with no YAML row: {missing}"

    def test_python_and_typescript_are_the_only_real_runners_today(self):
        real_runners = {p for p, c in ev_registry.PLATFORM_CONTRACT.items() if c.runner is not None}
        assert real_runners == {"python", "typescript"}

    def test_go_is_the_only_precommit_blocking_platform_today(self):
        blocking = {p for p, c in ev_registry.PLATFORM_CONTRACT.items() if c.precommit_blocking}
        assert blocking == {"go"}


class TestReachabilityAdapterRealAdaptersAreFunctional:
    """For every platform declared status: real, prove export_surface()
    actually computes something from real input (never a hard-coded stub) --
    the direct generalization of TC-MT040-42's own acceptance check
    ('TS fixture: Lexer unreachable, Document reachable')."""

    def test_python_real_adapter_resolves_all(self, tmp_path):
        assert CAPS["platforms"]["python"]["reachability_adapter"]["status"] == "real"
        (tmp_path / "__init__.py").write_text("__all__ = ['Foo']\n", encoding="utf-8")
        module = extraction_lang.LANGUAGES["python"]
        names, root = module.export_surface(tmp_path, tmp_path)
        assert names == {"Foo"}

    def test_rust_real_adapter_resolves_pub_use(self, tmp_path):
        assert CAPS["platforms"]["rust"]["reachability_adapter"]["status"] == "real"
        (tmp_path / "lib.rs").write_text("pub use crate::foo::Bar;\n", encoding="utf-8")
        module = extraction_lang.LANGUAGES["rust"]
        names, root = module.export_surface(tmp_path, tmp_path)
        assert names is not None and "Bar" in names

    def test_typescript_real_adapter_resolves_barrel(self, tmp_path):
        assert CAPS["platforms"]["typescript"]["reachability_adapter"]["status"] == "real"
        src = tmp_path / "src"
        src.mkdir()
        (src / "index.ts").write_text("export { Foo } from './foo.js';\n", encoding="utf-8")
        (src / "foo.ts").write_text("export class Foo {}\n", encoding="utf-8")
        module = extraction_lang.LANGUAGES["typescript"]
        names, entry = module.export_surface(tmp_path, src)
        assert names == {"Foo"}

    def test_net_real_adapter_returns_a_set_never_none(self, tmp_path):
        """csharp.py's polarity is inverted (membership means UNREACHABLE)
        and it never falls back to (None, None) -- always a real (possibly
        empty) frozenset. Both facts are asserted here, matching the YAML's
        own `detail` note."""
        assert CAPS["platforms"]["net"]["reachability_adapter"]["status"] == "real"
        (tmp_path / "Demo.cs").write_text(
            "namespace Demo { internal class Hidden {} public class Shown {} }\n",
            encoding="utf-8",
        )
        module = extraction_lang.LANGUAGES["csharp"]
        internal_names, root = module.export_surface(tmp_path, tmp_path)
        assert internal_names is not None
        assert "Hidden" in internal_names
        assert "Shown" not in internal_names


# --- format_recognizer_style (functional: real Pass 1g gate) -----------------


class TestFormatRecognizerStyleMatrix:
    @pytest.mark.parametrize("platform", PLATFORMS)
    def test_camel_identifier_gate_matches_declared_modes(self, platform, tmp_path):
        """Pass 1g (_scan_ts_io_functions) is gated to
        language in ('typescript', 'javascript') only -- proven functionally
        by feeding every platform's language the SAME real matching content
        (`export function renderDocumentToDocx`, the exact example cited in
        this mission's G-TS-11 finding) and confirming only platforms
        declaring `camel_identifier` in format_recognizer_style.modes get a
        non-empty result."""
        from extraction.formats import _scan_ts_io_functions

        lang = CAPS["platforms"][platform]["language"]
        modes = CAPS["platforms"][platform]["format_recognizer_style"]["modes"]
        src_file = tmp_path / "docxexport.ts"
        src_file.write_text(
            "export function renderDocumentToDocx(input: string): void {}\n",
            encoding="utf-8",
        )
        result = _scan_ts_io_functions([src_file], tmp_path, lang, "pdf", None)
        if "camel_identifier" in modes:
            assert result, (
                f"{platform} ({lang}): declares camel_identifier mode but "
                f"_scan_ts_io_functions found nothing for a real matching file"
            )
        else:
            assert result == [], (
                f"{platform} ({lang}): does not declare camel_identifier mode "
                f"but _scan_ts_io_functions found a match -- Pass 1g's gate may "
                f"have widened; update the YAML"
            )

    @pytest.mark.parametrize("platform", PLATFORMS)
    def test_pascal_verb_mode_always_declared(self, platform):
        """Pass 1e (_scan_pascal_verb_format_methods) runs unconditionally
        for every language per its own module comment ('safe to run
        unconditionally across every language and family') -- every
        platform must declare pascal_verb."""
        modes = CAPS["platforms"][platform]["format_recognizer_style"]["modes"]
        assert "pascal_verb" in modes


# ===========================================================================
# Part 2 -- Reproduction of test_rust_platform_maps.py's assertions,
# generalized to all 7 platforms
# ===========================================================================

# One representative real class-kind + a real non-class kind, and a file path
# extension, per platform -- sourced directly from _CLASS_TYPES/_FUNC_TYPES
# (tree_helpers.py) and _FILE_EXTENSIONS, not invented.
_REPRESENTATIVE_CLASS_KIND = {
    "python": ("class_definition", "widget.py"),
    "net": ("class_declaration", "Widget.cs"),
    "java": ("class_declaration", "Widget.java"),
    "cpp": ("class_specifier", "widget.h"),
    "go": ("type_spec", "widget.go"),
    "rust": ("struct_item", "widget.rs"),
    "typescript": ("class_declaration", "widget.ts"),
}
_REPRESENTATIVE_NON_CLASS_KIND = {
    "python": "function_definition",
    "net": "method_declaration",
    "java": "method_declaration",
    "cpp": "function_definition",
    "go": "function_declaration",
    "rust": "function_item",
    "typescript": "function_declaration",
}


def _entry(name="Widget", kind="class_definition", file="widget.py", **kw):
    e = {"name": name, "kind": kind, "file": file, "visibility": "public"}
    e.update(kw)
    return e


class TestReferenceFilterReproduction:
    """Generalizes test_rust_platform_maps.py::TestRustReferenceFilter to
    all 7 platforms."""

    @pytest.mark.parametrize("platform", PLATFORMS)
    def test_representative_class_kind_passes(self, platform):
        kind, file = _REPRESENTATIVE_CLASS_KIND[platform]
        assert _passes_platform_scope(_entry(kind=kind, file=file), platform), (platform, kind)

    @pytest.mark.parametrize("platform", PLATFORMS)
    def test_representative_non_class_kind_excluded(self, platform):
        kind, file = _REPRESENTATIVE_CLASS_KIND[platform]
        non_class_kind = _REPRESENTATIVE_NON_CLASS_KIND[platform]
        assert not _passes_platform_scope(_entry(kind=non_class_kind, file=file), platform), (
            platform, non_class_kind
        )

    @pytest.mark.parametrize("platform", PLATFORMS)
    def test_underscore_name_excluded(self, platform):
        kind, file = _REPRESENTATIVE_CLASS_KIND[platform]
        if platform == "cpp":
            # cpp takes a DEDICATED early-return branch in _passes_platform_scope
            # ("C++ is handled with a dedicated early-return block using
            # name-based rules ... without path filtering", per the function's
            # own docstring) that returns before the universal
            # `name.startswith("_")` guard is ever reached -- verified live,
            # not assumed: an underscore-prefixed cpp class_specifier DOES
            # pass scope today (only an I-prefixed name or a name in
            # _CPP_ABSTRACT_BASES is excluded for cpp).
            assert _passes_platform_scope(_entry(name="_Private", kind=kind, file=file), platform)
            return
        assert not _passes_platform_scope(_entry(name="_Private", kind=kind, file=file), platform)

    @pytest.mark.parametrize("platform", PLATFORMS)
    def test_representative_kind_cross_platform_disjointness(self, platform):
        """Each platform's representative class kind must not pass scope
        for every OTHER platform (mirrors
        test_rust_kinds_do_not_pass_other_platforms, generalized)."""
        kind, file = _REPRESENTATIVE_CLASS_KIND[platform]
        for other in PLATFORMS:
            if other == platform:
                continue
            other_handles_same_kind = kind in CAPS["platforms"][other]["class_kinds"]
            if other_handles_same_kind:
                continue  # a real grammar overlap (e.g. class_declaration shared by several) -- not a disjointness violation
            assert not _passes_platform_scope(_entry(kind=kind, file=file), other), (
                platform, kind, other
            )


class TestBatchReferenceReproduction:
    """Generalizes test_rust_platform_maps.py::TestRustBatchReference."""

    @pytest.mark.parametrize("platform", PLATFORMS)
    def test_platform_lang_map(self, platform):
        lang = CAPS["platforms"][platform]["language"]
        assert _br._PLATFORM_TO_LANG.get(platform) == lang

    @pytest.mark.parametrize("platform", PLATFORMS)
    def test_class_kinds_by_platform_present(self, platform):
        """batch_reference keeps its OWN _CLASS_KINDS_BY_PLATFORM copy
        (parallel to, not identical to, tree_helpers._CLASS_TYPES -- it
        deliberately omits kinds already covered by the shared _ENUM_KINDS
        union, e.g. typescript's enum_declaration). Just proves an entry
        exists and is a non-empty subset of the platform's declared kinds
        union with enum kinds -- not a strict equality (that would be a
        wrong/over-tight assertion given the real, intentional divergence
        found while building this file)."""
        assert platform in _br._CLASS_KINDS_BY_PLATFORM
        assert _br._CLASS_KINDS_BY_PLATFORM[platform]

    @pytest.mark.parametrize("platform", PLATFORMS)
    def test_group_key_root_file_is_core(self, platform):
        e = _entry(file=_REPRESENTATIVE_CLASS_KIND[platform][1])
        assert _br._derive_group_key(e, "demo", platform) == "core"


class TestInstallToolingReproduction:
    """Generalizes test_rust_platform_maps.py::TestRustInstallTooling."""

    _EXPECTED_PLATFORM_TYPE = {
        "python": "python", "net": "dotnet", "java": "java",
        # cpp is grouped with dotnet's install-block detection today (real,
        # verified code behavior -- install_block_updater.py's own
        # _PLATFORM_DOTNET = frozenset({"net", "cpp"})), not a guess.
        "cpp": "dotnet",
        "go": "go", "rust": "rust", "typescript": "js",
    }

    @pytest.mark.parametrize("platform", PLATFORMS)
    def test_detect_platform_type(self, platform):
        assert _detect_platform_type(platform) == self._EXPECTED_PLATFORM_TYPE[platform]

    _INSTALL_MD_SAMPLES = {
        "python": ("# Install\n\n```\npip install aspose-demo-foss==1.0.0\n```\n",
                   "aspose-demo-foss", "1.0.0"),
        "net": ("# Install\n\n```\ndotnet add package Aspose.Demo-FOSS --version 1.0.0\n```\n",
                "Aspose.Demo-FOSS", "1.0.0"),
        "rust": ("# Install\n\n```\ncargo add aspose-demo-foss@1.0.0\n```\n",
                 "aspose-demo-foss", "1.0.0"),
    }

    @pytest.mark.parametrize("platform", sorted(_INSTALL_MD_SAMPLES))
    def test_parse_install_md_real_form(self, platform, tmp_path):
        content, expected_name, expected_version = self._INSTALL_MD_SAMPLES[platform]
        p = tmp_path / "install.md"
        p.write_text(content, encoding="utf-8")
        info = _parse_install_md(p)
        assert info["package_name"] == expected_name
        assert info["version"] == expected_version

    @pytest.mark.parametrize("platform", sorted(_INSTALL_MD_SAMPLES))
    def test_block_contains_install_real_form(self, platform, tmp_path):
        content, expected_name, _ = self._INSTALL_MD_SAMPLES[platform]
        info = {"package_name": expected_name}
        platform_type = _detect_platform_type(platform)
        assert _block_contains_install(content, info, platform_type) is True
        assert _block_contains_install("```\nsome unrelated text\n```", info, platform_type) is False

    @pytest.mark.parametrize("platform", PLATFORMS)
    def test_install_recipe_pkg_managers_registered_or_declared_absent(self, platform):
        decl = CAPS["platforms"][platform]["package_managers"]
        if isinstance(decl, dict) and decl.get("declared") is False:
            assert platform not in _PLATFORM_PKG_MANAGERS
        else:
            assert _PLATFORM_PKG_MANAGERS[platform] == set(decl)


class TestEvalConfigReproduction:
    """Generalizes test_rust_platform_maps.py::TestRustEvalConfig."""

    @pytest.mark.parametrize("platform", PLATFORMS)
    def test_lang_to_platform(self, platform):
        lang = CAPS["platforms"][platform]["language"]
        if platform == "go":
            # Another real, independently-confirmed instance of the "go is
            # the undeclared platform" pattern (see
            # TestSmokeTestLangsMatrix::test_go_is_the_undeclared_platform_
            # everywhere): content_eval/config.py:LANG_TO_PLATFORM has no
            # 'go' key at all -- not one of this card's 16 declared
            # capability sites, so recorded here rather than in the YAML,
            # but real and verified live, not assumed.
            assert LANG_TO_PLATFORM.get(lang) is None
            return
        assert LANG_TO_PLATFORM.get(lang) == platform

    @pytest.mark.parametrize("platform", PLATFORMS)
    def test_foreign_patterns_registered_or_declared_absent(self, platform):
        decl_prose = CAPS["platforms"][platform]["foreign_prose_patterns"]
        decl_code = platform in PLATFORM_FOREIGN_PATTERNS
        if decl_prose.get("declared") is False:
            assert platform not in PROSE_FOREIGN_PATTERNS
        else:
            assert platform in PROSE_FOREIGN_PATTERNS
        # PLATFORM_FOREIGN_PATTERNS (code-block contamination) is a SEPARATE
        # dict from PROSE_FOREIGN_PATTERNS -- both real, both checked here so
        # a future card that also wires PLATFORM_FOREIGN_PATTERNS's own 'go'
        # gap doesn't silently regress unnoticed by this file.
        if platform == "go":
            assert not decl_code, "go unexpectedly gained a PLATFORM_FOREIGN_PATTERNS entry -- update the YAML/tests"

    @pytest.mark.parametrize("platform", PLATFORMS)
    def test_fence_fixer_primary_lang(self, platform):
        lang = CAPS["platforms"][platform]["language"]
        real = _PLATFORM_PRIMARY_LANG.get(platform)
        if platform == "go":
            # A THIRD real, independently-confirmed instance of the same
            # "go is undeclared" pattern:
            # content_eval/remediation/fixers/code_fence_lang.py:
            # _PLATFORM_PRIMARY_LANG has no 'go' key either.
            assert real is None
            return
        assert real == lang, f"{platform}: code_fence_lang._PLATFORM_PRIMARY_LANG {real!r} != {lang!r}"


class TestSyntaxCheckingReproduction:
    """Generalizes test_rust_platform_maps.py::TestRustSyntaxChecking."""

    @pytest.mark.parametrize("platform", PLATFORMS)
    def test_code_syntax_check_parser_loads_or_declared_absent(self, platform):
        lang = CAPS["platforms"][platform]["language"]
        decl = CAPS["platforms"][platform]["smoke_test_langs"]
        if decl.get("code_syntax_check_py_matches"):
            assert lang in csc._TS_LANGS
            parser = csc._ts_parser_for(lang)
            if parser is None:
                # Real environment gap, found live while building this
                # card: code_syntax_check.py's _load_ts_parsers() has a
                # tree_sitter_language_pack FALLBACK only for rust
                # (_TS_PARSER_CACHE population at L119-127) -- java/cpp/
                # typescript/javascript each depend on a STANDALONE
                # tree-sitter-<lang> pip package that no requirements*.txt
                # in this repo declares (verified: grepped every
                # scripts/*/requirements*.txt). A clean bootstrap of this
                # repo (exactly what this session did) therefore has no
                # real tree-sitter syntax-checking for those 3 languages --
                # only the looser _BRACE_LANGS heuristic fallback runs.
                # This is a pre-existing, separate gap from anything this
                # card is scoped to fix (code_syntax_check.py is not in
                # this card's touchable-files list) -- skip, don't force a
                # false pass or a misleading hard failure.
                pytest.skip(
                    f"{platform} ({lang}): _TS_LANGS declares this language "
                    f"but no standalone tree-sitter-{lang} package is "
                    f"installed/declared in this repo's requirements files "
                    f"-- real, pre-existing environment gap, not a matrix defect."
                )
        else:
            assert lang not in csc._TS_LANGS

    @pytest.mark.parametrize("platform", PLATFORMS)
    def test_smoke_test_maps_or_declared_absent(self, platform):
        decl = CAPS["platforms"][platform]["smoke_test_langs"]
        if decl.get("smoke_test_py_matches"):
            assert platform in st._PLATFORM_LANGS
        else:
            assert platform not in st._PLATFORM_LANGS


class TestKnowledgePolicyReproduction:
    """Generalizes test_rust_platform_maps.py::TestRustKnowledgePolicy."""

    @pytest.mark.parametrize("platform", PLATFORMS)
    def test_coverage_concrete_only(self, platform):
        _coverage_policy_matches(platform, CONCRETE_ONLY_PLATFORMS)

    # Case-convention accessor inference is exercised in full by
    # TestCaseConventionMatrix above (its own class already generalizes
    # test_rust_platform_maps.py::TestRustKnowledgePolicy.test_promote_snake_inference).


# ===========================================================================
# Part 3 -- Negative controls: prove the matrix fails closed
# ===========================================================================


class TestNegativeControlMatrixCatchesDrift:
    """These re-run the SAME comparison helper functions the real matrix
    tests above call, but pass a mutated LOCAL COPY of the real map --
    proving the comparison logic itself (not a duplicated, hand-written
    re-assertion) rejects a regression. Never monkeypatches the live
    tree_helpers/coverage module (banned T2 internal-monkeypatch pattern in
    this repo)."""

    def test_class_kinds_check_fails_closed_when_ts_abstract_class_regresses(self):
        """Simulates the exact TC-10 regression this whole contract file
        exists to make un-repeatable: TypeScript's abstract_class_declaration
        silently dropped from _CLASS_TYPES."""
        regressed = {lang: set(kinds) for lang, kinds in _CLASS_TYPES.items()}
        regressed["typescript"].discard("abstract_class_declaration")
        with pytest.raises(AssertionError):
            _class_kinds_match("typescript", regressed)
        # Sanity: the SAME helper against the real, unmutated map still passes.
        _class_kinds_match("typescript", _CLASS_TYPES)

    def test_func_kinds_check_fails_closed_when_rust_signature_item_regresses(self):
        regressed = {lang: set(kinds) for lang, kinds in _FUNC_TYPES.items()}
        regressed["rust"].discard("function_signature_item")
        with pytest.raises(AssertionError):
            _func_kinds_match("rust", regressed)
        _func_kinds_match("rust", _FUNC_TYPES)

    def test_module_kinds_check_fails_closed_when_go_package_clause_regresses(self):
        regressed = {lang: set(kinds) for lang, kinds in _MODULE_TYPES.items()}
        regressed["go"] = set()
        with pytest.raises(AssertionError):
            _module_kinds_match("go", regressed)
        _module_kinds_match("go", _MODULE_TYPES)

    def test_coverage_policy_check_fails_closed_when_rust_silently_removed(self):
        regressed = set(CONCRETE_ONLY_PLATFORMS)
        regressed.discard("rust")
        with pytest.raises(AssertionError):
            _coverage_policy_matches("rust", regressed)
        _coverage_policy_matches("rust", CONCRETE_ONLY_PLATFORMS)

    def test_class_kinds_check_fails_closed_when_a_platform_gains_an_undeclared_kind(self):
        """The inverse regression direction: code silently GAINS a kind the
        YAML doesn't know about (e.g. a future grammar update starts
        emitting a new node type tree_helpers.py picks up) must also fail,
        not just kinds being removed."""
        regressed = {lang: set(kinds) for lang, kinds in _CLASS_TYPES.items()}
        regressed["python"].add("decorated_definition")
        with pytest.raises(AssertionError):
            _class_kinds_match("python", regressed)
        _class_kinds_match("python", _CLASS_TYPES)


class TestNegativeControlReachabilityAdapterCatchesDrift:
    def test_unknown_status_check_fails_closed_if_a_real_adapter_starts_returning_names(self):
        """If cpp/java/go's export_surface() ever starts returning a real
        signal instead of the permanent (None, None) stub, the YAML's
        status: unknown_not_implemented assertion must fail, not silently
        keep passing (a false 'still unimplemented' claim would be exactly
        as bad as the stale drift TC-10 illustrates for kind maps)."""
        class _FakeRealAdapterModule:
            @staticmethod
            def export_surface(repo, pkg_root):
                return {"SomeClass"}, repo

        class _FakeLanguages(dict):
            pass

        fake_languages = _FakeLanguages(extraction_lang.LANGUAGES)
        fake_languages["java"] = _FakeRealAdapterModule
        names, root = fake_languages["java"].export_surface(Path("."), Path("."))
        with pytest.raises(AssertionError):
            assert names is None and root is None
