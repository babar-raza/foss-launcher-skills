"""MT074 G-1 generality lint.

The fleet-propagation machinery must work for ANY family/platform. This test fails if a generic
module hard-codes a product, feature or format literal in executable code (identifiers or string
constants -- docstrings and comments are exempt because they may cite incidents).

Matching is TOKEN based (R4-10): every identifier / string is split on `_`, camelCase and any
non-alphanumeric character, and each token is compared case-insensitively against the forbidden
and toolchain sets. A plain `\\b(pdf|...)\\b` regex misses `pdf_path`, `handle_xlsx_export` and
`PdfSaveOptions` because `_` is a word character and camelCase has no boundary.

Language adapters legitimately name concrete toolchains (a Java adapter must say `javap`), so the
`java`/`jar`/`maven` tokens are allowed ONLY in the modules listed in LANGUAGE_SPECIFIC_ALLOWED.
"""
from __future__ import annotations

import ast
import re
from pathlib import Path

import pytest

_REPO = Path(__file__).resolve().parents[3]
_P = _REPO / "scripts" / "pipeline"

GENERIC_MODULES = [
    "lib/content_propagation_state.py",
    "lib/language_adapters.py",
    "lib/capability_delta.py",
    "lib/availability.py",
    "lib/propagation_analyzer.py",
    "commands/diagnostics/fleet_drift.py",
    "commands/diagnostics/propagation_analyze.py",
    "commands/ops/capability_surface_gate.py",
    "commands/ops/capability_ledger.py",
    "commands/ops/skill_provenance_audit.py",
    "commands/content/rendered_page_audit.py",
]
CONFIG_FILES = [
    "config/capability_placement.yaml",
    "config/skill_file_class_matrix.yaml",
]
# product / feature / format literals that must never appear in generic code or config
# Distinctive product/feature tokens only: common English words ("words", "cells", "slides", "markdown") are not linted --
# they appear legitimately as variable names and as output-format names in help text.
FORBIDDEN_TOKENS = frozenset({"pdf", "xlsx", "excel", "docx", "aspose"})
# Hugo site domains (reference/docs/kb/blog/products .aspose.org) are repository structure, not product literals.
_SITE_DOMAIN = re.compile(r"\b[a-z]+\.aspose\.org\b", re.IGNORECASE)
# toolchain tokens permitted only where a concrete language toolchain is the point
# `maven`/`npm`/`pypi` are registry-type identifiers (generic ecosystem names), not language toolchains.
TOOLCHAIN_TOKENS = frozenset({"java", "javap", "javac", "jar"})
# Repo-wide environment-variable names that merely contain a forbidden word. They are an
# environment contract of this repository, not a product reference, and are stripped (exact
# names only) before token matching.
ALLOWED_ENV_NAMES = frozenset({"ASPOSE_CLONE_CACHE"})
# Narrow, per-module token allowances. Scoped by module path: the same token anywhere else fails.
PER_MODULE_ALLOWED_TOKENS = {
    # generic file-extension list (media/asset suffixes), not a product reference
    "commands/content/rendered_page_audit.py": frozenset({"pdf"}),
}
LANGUAGE_SPECIFIC_ALLOWED = {"lib/language_adapters.py", "lib/availability.py"}
# strings that legitimately contain a forbidden word as part of a generic mechanism
ALLOWED_STRINGS = {
    # skill ids / file classes in the provenance audit's DATA-driven defaults are not literals of this module
}

# one token = an acronym run before a Capitalised word ("PDFSave" -> PDF, Save), a Capitalised or
# lower-case word, a remaining upper-case run, or a digit run
_TOKEN_PART = re.compile(r"[A-Z]+(?=[A-Z][a-z])|[A-Z]?[a-z]+|[A-Z]+|[0-9]+")


def _tokens(text: str) -> set[str]:
    """Lower-cased tokens of ``text`` split on non-alphanumerics, `_` and camelCase."""
    out: set[str] = set()
    for name in ALLOWED_ENV_NAMES:
        text = text.replace(name, " ")
    for chunk in re.split(r"[^A-Za-z0-9]+", _SITE_DOMAIN.sub(" ", text)):
        out.update(m.group(0).lower() for m in _TOKEN_PART.finditer(chunk))
    return out


def _has_forbidden(text: str, rel: str | None = None) -> bool:
    allowed = PER_MODULE_ALLOWED_TOKENS.get(rel, frozenset()) if rel else frozenset()
    return bool(_tokens(text) & (FORBIDDEN_TOKENS - allowed))


def _has_toolchain(text: str) -> bool:
    return bool(_tokens(text) & TOOLCHAIN_TOKENS)


def _docstring_nodes(tree: ast.AST) -> set[int]:
    ids: set[int] = set()
    for node in ast.walk(tree):
        if isinstance(node, (ast.Module, ast.ClassDef, ast.FunctionDef, ast.AsyncFunctionDef)):
            body = getattr(node, "body", [])
            if body and isinstance(body[0], ast.Expr) and isinstance(getattr(body[0], "value", None), ast.Constant) \
                    and isinstance(body[0].value.value, str):
                ids.add(id(body[0].value))
    return ids


def _scan_source(source: str) -> list[tuple[int, str]]:
    """Every identifier and string constant of executable code (docstrings excluded)."""
    tree = ast.parse(source)
    skip = _docstring_nodes(tree)
    found: list[tuple[int, str]] = []

    def add(node: ast.AST, text: str | None) -> None:
        if text:
            found.append((getattr(node, "lineno", 0), text))

    # ast.walk also visits the str Constant parts inside ast.JoinedStr (f-strings).
    for node in ast.walk(tree):
        if isinstance(node, ast.Constant) and isinstance(node.value, str) and id(node) not in skip:
            add(node, node.value)
        elif isinstance(node, ast.Name):
            add(node, node.id)
        elif isinstance(node, ast.Attribute):
            add(node, node.attr)
        elif isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef, ast.ClassDef)):
            add(node, node.name)
        elif isinstance(node, ast.arg):
            add(node, node.arg)
        elif isinstance(node, ast.keyword):  # call-site `f(pdf_path=...)`; arg is None for **kwargs
            add(node, node.arg)
        elif isinstance(node, ast.alias):  # `import x as pdf_helper`, `from m import PdfThing`
            add(node, node.name)
            add(node, node.asname)
        elif isinstance(node, ast.ImportFrom):
            add(node, node.module)
        elif isinstance(node, ast.ExceptHandler):
            add(node, node.name)
        elif isinstance(node, (ast.Global, ast.Nonlocal)):
            for name in node.names:
                add(node, name)
    return found


def _executable_strings_and_names(path: Path) -> list[tuple[int, str]]:
    return _scan_source(path.read_text(encoding="utf-8"))


@pytest.mark.parametrize("rel", GENERIC_MODULES)
def test_generic_module_has_no_product_or_feature_literals(rel):
    path = _P / rel
    assert path.is_file(), f"{rel} missing"
    bad = [(ln, s[:80]) for ln, s in _executable_strings_and_names(path) if _has_forbidden(s, rel)]
    assert not bad, f"{rel}: product/feature literals in executable code: {bad[:8]}"


@pytest.mark.parametrize("rel", [m for m in GENERIC_MODULES if m not in LANGUAGE_SPECIFIC_ALLOWED])
def test_non_adapter_modules_have_no_toolchain_literals(rel):
    path = _P / rel
    bad = [(ln, s[:80]) for ln, s in _executable_strings_and_names(path) if _has_toolchain(s)]
    assert not bad, f"{rel}: concrete-toolchain literals outside a language adapter: {bad[:8]}"


@pytest.mark.parametrize("rel", CONFIG_FILES)
def test_config_has_no_product_or_feature_literals(rel):
    text = (_P / rel).read_text(encoding="utf-8")
    code_lines = [(i, ln) for i, ln in enumerate(text.splitlines(), 1) if not ln.lstrip().startswith("#")]
    bad = [(i, ln.strip()[:90]) for i, ln in code_lines if _has_forbidden(ln)]
    assert not bad, f"{rel}: product/feature literals in config: {bad[:8]}"


def test_language_api_paths_yaml_only_uses_platform_keys_as_data():
    """language_api_paths.yaml may name languages (they are DATA keyed by platform) but never products/features."""
    text = (_P / "config/language_api_paths.yaml").read_text(encoding="utf-8")
    code = [ln for ln in text.splitlines() if not ln.lstrip().startswith("#")]
    bad = [ln.strip()[:90] for ln in code if _has_forbidden(ln)]
    assert not bad, f"language_api_paths.yaml: product/feature literals: {bad[:8]}"


# ---- self-tests: the lint itself must catch what the old word-boundary regex missed ----------------

_OLD_FORBIDDEN = re.compile(r"\b(pdf|xlsx|excel|docx|aspose)\b", re.IGNORECASE)
_OLD_TOOLCHAIN = re.compile(r"\b(java|javap|javac|jar)\b", re.IGNORECASE)


@pytest.mark.parametrize("identifier", ["pdf_path", "handle_xlsx_export", "PdfSaveOptions", "DocxWriter", "to_excel_sheet"])
def test_token_matching_catches_identifiers_the_word_regex_missed(identifier):
    assert not _OLD_FORBIDDEN.search(identifier), "premise: the old regex really missed this"
    assert _has_forbidden(identifier)
    for source in (f"{identifier} = 1", f"def {identifier}(): pass", f"class {identifier}: pass",
                   f"x.{identifier}", f"f({identifier}=1)", f"def g({identifier}): pass"):
        assert any(_has_forbidden(s) for _, s in _scan_source(source)), source


@pytest.mark.parametrize("identifier", ["jar_path", "run_javap", "JavaDocParser", "build_jar_index"])
def test_token_matching_catches_toolchain_identifiers_the_word_regex_missed(identifier):
    assert not _OLD_TOOLCHAIN.search(identifier)
    assert _has_toolchain(identifier)
    assert any(_has_toolchain(s) for _, s in _scan_source(f"{identifier} = 1"))


def test_walk_covers_keyword_alias_and_fstring_parts():
    cases = {
        "keyword": "run(pdf_path=1)",
        "alias-name": "import helpers as pdf_helpers",
        "alias-from": "from helpers import PdfSaveOptions",
        "import-from-module": "from xlsx_tools import thing",
        "fstring-constant": "x = f'{value}/out.pdf'",
        "except-name": "try:\n    pass\nexcept Exception as pdf_error:\n    pass",
        "global": "def g():\n    global pdf_state\n    pdf_state = 1",
    }
    for label, source in cases.items():
        assert any(_has_forbidden(s) for _, s in _scan_source(source)), label


def test_token_matching_has_no_false_positives_on_neighbouring_words():
    for ok in ("jargon", "javascript", "upload_path", "expdf", "spreadsheet", "documents", "blog.aspose.org",
               "reference.aspose.org/en/x"):
        assert not _has_forbidden(ok) and not _has_toolchain(ok), ok
    # docstrings are exempt (they may cite incidents); executable strings are not
    assert _scan_source('"""pdf incident"""\nx = 1') == [(2, "x")]


def test_skill_provenance_audit_no_longer_needs_a_language_allowance():
    assert "commands/ops/skill_provenance_audit.py" not in LANGUAGE_SPECIFIC_ALLOWED


def test_env_name_allowance_is_exact():
    assert not _has_forbidden("ASPOSE_CLONE_CACHE")
    assert not _has_forbidden("os.environ.get('ASPOSE_CLONE_CACHE')")
    assert _has_forbidden("ASPOSE_OTHER_SETTING")
    assert _has_forbidden("ASPOSE_CLONE_CACHE_aspose")


def test_per_module_token_allowance_is_scoped():
    allowed_rel = "commands/content/rendered_page_audit.py"
    snippet = "EXTS = 'html css pdf zip'"
    texts = [t for _, t in _scan_source(snippet)]
    assert not any(_has_forbidden(t, allowed_rel) for t in texts)
    # same token in any other module (or with no module) still fails
    assert any(_has_forbidden(t, "commands/ops/other_module.py") for t in texts)
    assert any(_has_forbidden(t) for t in texts)
    # the allowance covers only the listed token
    assert _has_forbidden("docx", allowed_rel)
