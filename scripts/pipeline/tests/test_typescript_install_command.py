"""Tests for the TypeScript/npm install-command fix, Mission
MT040-2026-08-28-PDF-TYPESCRIPT-LAUNCH (TC-MT040-46).

Covers four previously-untested surfaces that all fed the same "npm install
{guessed-name}" defect shape, plus a repo-wide anti-regression guard:

1. commands/knowledge/index.py::_install_command's typescript branch, now
   registry-backed via lib/product_registry.py instead of the old hardcoded
   `npm install aspose-{family}-foss`.
2. commands/ops/batch_gen_missing.py's generated page content, now resolving
   the typescript package name through the same shared loader instead of the
   old hand-maintained PACKAGE_NAMES dict.
3. Two narrow regex bugs that both mishandled a scoped npm package name's own
   "@" character when a version suffix was present:
   commands/content/install_block_updater.py::_parse_install_md and
   content_eval/evaluators/install_recipe.py::_normalize_pkg_token.
4. A repo-wide grep guard proving no OTHER hardcoded install-command
   regressed back in.
"""

import json
import re
import sys
from pathlib import Path

import pytest

_PIPELINE_ROOT = Path(__file__).resolve().parents[1]
if str(_PIPELINE_ROOT) not in sys.path:
    sys.path.insert(0, str(_PIPELINE_ROOT))

import commands.knowledge.index as index_sut
import commands.ops.batch_gen_missing as batch_gen_sut
from commands.content.install_block_updater import _parse_install_md
from content_eval.evaluators.install_recipe import _normalize_pkg_token
from lib import product_registry


@pytest.fixture(autouse=True)
def isolate_paths(tmp_path):
    """Fresh temp knowledge_root/foss_packages_path per test, mirroring
    test_knowledge_index_install_command.py's own fixture. Also resets
    product_registry's own global config -- index.py's
    _typescript_install_command() self-syncs product_registry to
    FOSS_PACKAGES_PATH on every call, but batch_gen_missing.py has no
    configure() seam of its own and calls product_registry directly, so
    tests that exercise that path must reset it explicitly afterward to
    avoid leaking a tmp_path fixture into a later test."""
    index_sut.configure(knowledge_root=tmp_path / "knowledge", foss_packages_path=tmp_path / "package_registry.json")
    yield
    index_sut.configure(knowledge_root=None, foss_packages_path=None)
    product_registry.configure(products_path=None, exclusions_path=None, package_registry_path=None)


def _write_registry(tmp_path: Path, data: dict) -> None:
    (tmp_path / "package_registry.json").write_text(json.dumps(data), encoding="utf-8")


# ---------------------------------------------------------------------------
# 1. index.py::_install_command / _typescript_install_command
# ---------------------------------------------------------------------------

def test_typescript_published_entry_renders_real_command(tmp_path):
    _write_registry(tmp_path, {
        "pdf": {"typescript": {
            "registry_type": "npm",
            "candidate": {"name": "@asposefoss/pdf", "version": "0.1.0"},
            "verification": {"published": True},
        }}
    })
    result = index_sut._install_command("pdf", "typescript")
    assert result == "npm install @asposefoss/pdf@0.1.0"


def test_typescript_published_entry_with_no_candidate_version_omits_at_version(tmp_path):
    _write_registry(tmp_path, {
        "pdf": {"typescript": {
            "registry_type": "npm",
            "candidate": {"name": "@asposefoss/pdf"},
            "verification": {"published": True},
        }}
    })
    result = index_sut._install_command("pdf", "typescript")
    assert result == "npm install @asposefoss/pdf"


def test_typescript_unpublished_entry_never_fabricates_a_command(tmp_path):
    """The real cells/typescript shape: a scouted candidate name exists
    (excel-cells) but verification.published is False -- must render a
    placeholder, never a bare `npm install excel-cells` command."""
    _write_registry(tmp_path, {
        "cells": {"typescript": {
            "registry_type": "npm",
            "candidate": {"name": "excel-cells"},
            "verification": {"published": False},
        }}
    })
    result = index_sut._install_command("cells", "typescript")
    assert "npm install" not in result
    assert "not yet published on npm" in result
    assert "excel-cells" not in result


def test_typescript_missing_entry_falls_back_to_convention_then_placeholder(tmp_path):
    """No registry entry at all for this family/typescript -- get_package_name
    falls back to a naming-convention guess internally, but since there is no
    entry to confirm as published, _install_command must still render the
    same unpublished-style placeholder, never the guessed name as a live
    command."""
    _write_registry(tmp_path, {"other-family": {"typescript": {
        "registry_type": "npm",
        "candidate": {"name": "something-else"},
        "verification": {"published": True},
    }}})
    result = index_sut._install_command("widgets", "typescript")
    assert "npm install" not in result
    assert "not yet published on npm" in result


def test_typescript_missing_registry_file_degrades_gracefully_not_a_crash(tmp_path):
    # No package_registry.json written at all -- tmp_path/package_registry.json
    # does not exist.
    result = index_sut._install_command("cells", "typescript")
    assert "npm install" not in result
    assert "unavailable" in result


# ---------------------------------------------------------------------------
# 2. batch_gen_missing.py generated content
# ---------------------------------------------------------------------------

_API = {"Workbook": {"docstring": "Represents a document.", "methods": ["save"]}}
_SHA = "deadbeef"


def test_gen_docs_typescript_uses_registry_backed_name_never_generic_fallback(tmp_path):
    product_registry.configure(package_registry_path=tmp_path / "package_registry.json")
    _write_registry(tmp_path, {
        "cells": {"typescript": {
            "registry_type": "npm",
            "candidate": {"name": "excel-cells"},
            "verification": {"published": False},
        }}
    })
    pi = {"family": "cells", "platform": "typescript", "slug": "developer-guide/working-with-cells", "weight": 10}
    out = batch_gen_sut.gen_docs(pi, _API, _SHA)
    assert "npm install excel-cells" in out
    assert "aspose-cells-foss" not in out
    assert "@aspose/cells" not in out


def test_gen_docs_typescript_falls_back_when_registry_has_nothing(tmp_path):
    """No registry entry for this family at all -- product_registry's own
    naming-convention fallback fires (@asposefoss/{family}), never
    PACKAGE_NAMES's old foss.lower() shape for typescript."""
    product_registry.configure(package_registry_path=tmp_path / "package_registry.json")
    _write_registry(tmp_path, {})
    pi = {"family": "cells", "platform": "typescript", "slug": "developer-guide/working-with-cells", "weight": 10}
    out = batch_gen_sut.gen_docs(pi, _API, _SHA)
    assert "npm install @asposefoss/cells" in out


# ---------------------------------------------------------------------------
# 3a. install_block_updater.py::_parse_install_md -- scoped npm name + version
# ---------------------------------------------------------------------------

@pytest.mark.parametrize("command_line,expected_name,expected_version", [
    ("npm install @asposefoss/pdf@0.1.0", "@asposefoss/pdf", "0.1.0"),
    ("npm install aspose-3d@24.12.0", "aspose-3d", "24.12.0"),
    ("npm install @asposefoss/pdf", "@asposefoss/pdf", ""),
])
def test_parse_install_md_npm_scoped_name_and_version(tmp_path, command_line, expected_name, expected_version):
    install_md = tmp_path / "install.md"
    install_md.write_text(f"```bash\n{command_line}\n```\n", encoding="utf-8")
    result = _parse_install_md(install_md)
    assert result["package_name"] == expected_name
    assert result["version"] == expected_version


# ---------------------------------------------------------------------------
# 3b. install_recipe.py::_normalize_pkg_token -- scoped npm name + version
# ---------------------------------------------------------------------------

@pytest.mark.parametrize("token,expected", [
    ("@asposefoss/pdf@0.1.0", "@asposefoss/pdf"),
    ("@asposefoss/pdf", "@asposefoss/pdf"),
    ("aspose-3d@24.12.0", "aspose-3d"),
])
def test_normalize_pkg_token_npm_scoped_name_and_version(token, expected):
    assert _normalize_pkg_token(token) == expected


# ---------------------------------------------------------------------------
# 4. Repo-wide anti-regression guard
# ---------------------------------------------------------------------------
#
# Proves no OTHER hardcoded install-command shape regressed back in, mirroring
# the two patterns this taskcard just removed:
#   - `npm install aspose-{family}-foss` (index.py's old unconditional
#     f-string default -- every FOSS product's "family" was always
#     "aspose-{family}-foss" before scout-based verification existed).
#   - a hardcoded "@aspose/{family}" package-name literal (batch_gen_missing.py's
#     old PACKAGE_NAMES entries for ("3d","typescript")/("cells","typescript")).
#
# Scope and false-positive avoidance (read before "fixing" a failure here):
#   - Only scripts/pipeline/**/*.py, excluding scripts/pipeline/tests/ entirely
#     (per this taskcard's own instructions -- test fixture files legitimately
#     use these literal shapes as INPUT data for unrelated features, e.g.
#     test_gap_eval_profile_safety.py's typescript-import-extraction fixtures).
#   - Lines that are ENTIRELY a "#" comment are skipped. This is what lets
#     batch_gen_missing.py's own historical PACKAGE_NAMES docstring comment
#     (documenting the old, now-removed, hardcoded "@aspose/3d"/"@aspose/cells"
#     entries) and lib/token_ops.py's pre-existing, unrelated
#     "'@aspose/3d'" TS-import-example comment pass without a hand-maintained
#     exception -- neither is a hardcoded value actually being RETURNED.
#   - The scoped-literal pattern only matches a COMPLETE quoted literal
#     (`"@aspose/something"` with nothing but word-chars/./-/_ between the
#     slash and the closing quote) -- this is what lets
#     content_eval/evaluators/namespace_correctness.py's regex SOURCE strings
#     (e.g. `'@aspose/[\\w/-]+|aspose-[\\w-]+...'`, a pattern for DETECTING
#     mentions in content, not a hardcoded install command) pass: the regex
#     metacharacters right after "@aspose/" break the word-chars-only match
#     before it can reach a closing quote.
#   - index.py's own new _typescript_install_command() docstring mentions the
#     OLD hardcoded shape by name, inside backticks, as historical
#     documentation of the bug this taskcard fixed (not a "#" comment, so the
#     rule above doesn't cover it) -- that ONE exact line is allowlisted by
#     its exact stripped text below. If this line's wording ever changes, the
#     allowlist entry must be updated to match, or the guard will (correctly)
#     start flagging it again.
#
# If this test fails on a file/line NOT covered by the above, that is a real
# regression -- do not broaden the exclusions to silence it.

_GUARD_ROOT = _PIPELINE_ROOT
_GUARD_TESTS_DIR = _GUARD_ROOT / "tests"
_NPM_INSTALL_RE = re.compile(r"npm install aspose-")
_SCOPED_LITERAL_RE = re.compile(r"""["']@aspose/[A-Za-z0-9_.-]+["']""")

_KNOWN_LEGITIMATE_MENTIONS = {
    str(_GUARD_ROOT / "commands" / "knowledge" / "index.py"): {
        "unconditional `npm install aspose-{family}-foss` hardcode, which was the",
    },
}


def test_no_hardcoded_npm_install_command_regressed_in():
    violations = []
    for path in _GUARD_ROOT.rglob("*.py"):
        if _GUARD_TESTS_DIR == path.parent or _GUARD_TESTS_DIR in path.parents:
            continue
        try:
            text = path.read_text(encoding="utf-8")
        except (OSError, UnicodeDecodeError):
            continue
        allowed_lines = _KNOWN_LEGITIMATE_MENTIONS.get(str(path), set())
        for lineno, line in enumerate(text.splitlines(), start=1):
            stripped = line.strip()
            if stripped.startswith("#"):
                continue
            if stripped in allowed_lines:
                continue
            if _NPM_INSTALL_RE.search(line) or _SCOPED_LITERAL_RE.search(line):
                violations.append(f"{path}:{lineno}: {line.strip()}")

    assert not violations, (
        "Hardcoded install-command literal(s) found outside the known-legitimate "
        "allowlist -- see this test's own module-level comment block for scope "
        "and false-positive-avoidance rules:\n" + "\n".join(violations)
    )
