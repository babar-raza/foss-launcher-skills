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
    ("typescript", "npm install aspose-cells-foss"),
    ("net", "dotnet add package aspose.cells.foss"),
    ("go", "go get github.com/aspose-cells-foss/aspose-cells-foss-for-go"),
])
def test_non_java_platforms_unaffected_by_the_java_fix(tmp_path, platform, expected_substring):
    """Regression control for TC-MT008-03: fixing the Java branch must not
    touch the python/typescript/net/go branches."""
    result = sut._install_command("cells", platform)
    assert result == expected_substring
