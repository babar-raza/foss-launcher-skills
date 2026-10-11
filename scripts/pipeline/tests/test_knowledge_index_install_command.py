"""
Tests for commands/knowledge/index.py's _install_command / _java_install_command
(Mission MT008, TC-MT008-03; repointed to data/package_registry.json by Mission
MT015-2026-07-30-PACKAGE-REGISTRY).

Regression pin: for 3 months, the Java branch hardcoded `groupId=com.aspose`
unconditionally -- always exercised in practice because promote.py strips
`install_command` from merged/model.yaml (AF-03), so index.py's fallback path
was the ONLY path for every Java-FOSS family's install command. Fixed to read
the package-registry data file instead of hardcoding any groupId (including the
correct one) -- see Mission MT008 D-04 in plans/master-plan.md: hardcoding
`org.aspose` here would just be a different hardcode, not a fix to the
duplicated-authority root cause.
"""

import json
import sys
from pathlib import Path

import pytest

_PIPELINE_ROOT = Path(__file__).resolve().parents[1]
if str(_PIPELINE_ROOT) not in sys.path:
    sys.path.insert(0, str(_PIPELINE_ROOT))

import commands.knowledge.index as sut


@pytest.fixture(autouse=True)
def isolate_paths(tmp_path):
    """Each test gets a fresh temp knowledge_root/foss_packages_path."""
    sut.configure(knowledge_root=tmp_path / "knowledge", foss_packages_path=tmp_path / "package_registry.json")
    yield
    sut.configure(knowledge_root=None, foss_packages_path=None)


def _write_packages(tmp_path: Path, data: dict) -> None:
    (tmp_path / "package_registry.json").write_text(json.dumps(data), encoding="utf-8")


def test_java_published_family_uses_confirmed_coordinate(tmp_path):
    _write_packages(tmp_path, {
        "cells": {"java": {
            "registry_type": "maven",
            "candidate": {"group_id": "org.aspose", "artifact_id": "aspose-cells-foss", "version": "26.5.0"},
            "verification": {"published": True},
        }}
    })
    result = sut._install_command("cells", "java")
    assert "<groupId>org.aspose</groupId>" in result
    assert "<artifactId>aspose-cells-foss</artifactId>" in result
    assert "<version>26.5.0</version>" in result
    assert "com.aspose" not in result


def test_java_unpublished_family_never_fabricates_a_coordinate(tmp_path):
    _write_packages(tmp_path, {
        "slides": {"java": {"registry_type": "maven", "candidate": None, "verification": {"published": False}}}
    })
    result = sut._install_command("slides", "java")
    assert "groupId" not in result
    assert "not yet published" in result


def test_java_missing_family_never_fabricates_a_coordinate(tmp_path):
    _write_packages(tmp_path, {"cells": {"java": {
        "registry_type": "maven",
        "candidate": {"group_id": "org.aspose", "artifact_id": "aspose-cells-foss", "version": "26.5.0"},
        "verification": {"published": True},
    }}})
    result = sut._install_command("nonexistent-family", "java")
    assert "groupId" not in result
    assert "not yet published" in result


def test_java_missing_data_file_degrades_gracefully_not_a_crash(tmp_path):
    # No foss_packages.json written at all.
    result = sut._install_command("cells", "java")
    assert "groupId" not in result
    assert "unavailable" in result


def test_hardcoded_com_aspose_groupid_literal_is_gone():
    """Direct regression pin on the source text itself, not just behavior --
    catches a future re-hardcode even if it happens not to be exercised by
    the other tests' specific fixture data. Scoped to the actual harmful
    patterns (a quoted groupId literal or XML groupId content) rather than a
    bare substring match, which would false-positive on unrelated text like
    a `github.com/aspose-...` module path."""
    src = (_PIPELINE_ROOT / "commands" / "knowledge" / "index.py").read_text(encoding="utf-8")
    harmful_patterns = ['"com.aspose"', "'com.aspose'", ">com.aspose<"]
    for pattern in harmful_patterns:
        assert pattern not in src, f"a hardcoded com.aspose groupId literal ({pattern!r}) has crept back into index.py"


@pytest.mark.parametrize("platform,expected_substring", [
    ("python", "pip install aspose-cells-foss"),
    ("net", "dotnet add package aspose.cells.foss"),
    ("go", "go get github.com/aspose-cells-foss/aspose-cells-foss-for-go"),
])
def test_non_java_platforms_unaffected_by_the_java_fix(tmp_path, platform, expected_substring):
    """Regression control for TC-MT008-03: fixing the Java branch must not
    touch the python/net/go branches.

    NOTE (TC-MT040-46): "typescript" was removed from this parametrize. This
    fixture's autouse isolate_paths() points foss_packages_path at a tmp file
    that is never written for python/net/go (they don't read it at all), but
    typescript now DOES read it (see _typescript_install_command) -- so it
    structurally needs its own registry fixture, not a shared no-file
    assumption. See test_typescript_platform_is_registry_backed_not_hardcoded
    below for the direct replacement of the old
    ("typescript", "npm install aspose-cells-foss") row (that hardcoded
    expectation was itself the bug -- see scripts/pipeline/tests/
    test_typescript_install_command.py for full published/unpublished/
    missing-entry/missing-file coverage).
    """
    result = sut._install_command("cells", platform)
    assert result == expected_substring


def test_typescript_platform_is_registry_backed_not_hardcoded(tmp_path):
    """TC-MT040-46: replaces the old, wrong pre-existing assertion that
    _install_command("cells", "typescript") always returns the hardcoded
    "npm install aspose-cells-foss" shape (never a real npm-scoped package
    name, and never grounded in data/package_registry.json at all). The
    typescript branch now resolves through lib/product_registry.py exactly
    like the java branch resolves through data/package_registry.json
    directly -- proven here with a fixture registry entry this test
    controls (NOT the real repo's cells entry, which may change
    independently). Full published/unpublished/missing-entry/missing-file
    coverage lives in test_typescript_install_command.py; this is the
    single "the behavior changed, here's what it looks like now" pin in
    this file, colocated with the other _install_command platform rows for
    easy comparison."""
    _write_packages(tmp_path, {
        "cells": {"typescript": {
            "registry_type": "npm",
            "candidate": {"name": "excel-cells"},
            "verification": {"published": True},
        }}
    })
    result = sut._install_command("cells", "typescript")
    assert result == "npm install excel-cells"
    assert "aspose-cells-foss" not in result
