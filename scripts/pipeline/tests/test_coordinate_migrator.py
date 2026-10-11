"""
Tests for coordinate_migrator.py (TC-04).

8 test scenarios per the plan:
  T1: Java groupId change in Maven XML code block
  T2: Java artifactId change in Maven XML code block
  T3: Python package name change in pip install code block
  T4: .NET package name change in dotnet add package code block
  T5: Prose mention only (no code block) -> HUMAN_REVIEW_REQUIRED, 0 replacements
  T6: English-only guard (locale-suffixed file rejected)
  T7: Noop when old coordinate not present in file
  T8: Both code block replacement AND prose mention -> HUMAN_REVIEW_REQUIRED + replacements
"""

import json
import sys
from pathlib import Path

import pytest

_PIPELINE_ROOT = Path(__file__).resolve().parents[1]
if str(_PIPELINE_ROOT) not in sys.path:
    sys.path.insert(0, str(_PIPELINE_ROOT))

import commands.content.coordinate_migrator as sut

# ── Fixtures ───────────────────────────────────────────────────────────────

JAVA_CHANGES = [
    {"old": "com.aspose", "new": "org.aspose", "field": "group_id"},
    {"old": "cells-foss", "new": "aspose-cells-foss", "field": "artifact_id"},
]

PYTHON_CHANGES = [
    {"old": "aspose-old-pkg", "new": "aspose-new-pkg", "field": "package_name"},
]

DOTNET_CHANGES = [
    {"old": "Aspose.Old.Package", "new": "Aspose.New.Package", "field": "package_name"},
]


@pytest.fixture(autouse=True)
def isolate_repo(tmp_path):
    """Each test gets a fresh temp repo root."""
    sut.configure(repo_root=tmp_path)
    yield
    sut.configure(repo_root=None)


def _make_content_file(tmp_path: Path, rel_path: str, content: str) -> Path:
    p = tmp_path / rel_path
    p.parent.mkdir(parents=True, exist_ok=True)
    p.write_text(content, encoding="utf-8")
    return p


def _make_manifest_delta(
    tmp_path: Path, family: str, platform: str, coord_events: list
) -> Path:
    p = tmp_path / "knowledge" / family / platform / "merged" / "manifest_delta.json"
    p.parent.mkdir(parents=True, exist_ok=True)
    p.write_text(
        json.dumps({
            "coordinate_changes": coord_events,
            "install_cmd_changes": [],
            "version_changes": [],
        }),
        encoding="utf-8",
    )
    return p


# ── T1: Java groupId change in Maven XML code block ────────────────────────

def test_t1_java_group_id_replaced_in_code_block(tmp_path):
    """T1: groupId com.aspose -> org.aspose replaced inside Maven XML code block."""
    content = (
        "---\ntitle: Installation\n---\n\n"
        "## Maven\n\n"
        "```xml\n"
        "<dependency>\n"
        "  <groupId>com.aspose</groupId>\n"
        "  <artifactId>cells-foss</artifactId>\n"
        "  <version>1.0.0</version>\n"
        "</dependency>\n"
        "```\n"
    )
    page = _make_content_file(
        tmp_path,
        "content/docs.aspose.org/en/cells/java/getting-started/installation.md",
        content,
    )

    result = sut.migrate_coordinates(page, JAVA_CHANGES, dry_run=False)

    assert result["result"] == sut.R_MIGRATED
    assert result["replacements"] >= 1
    updated = page.read_text(encoding="utf-8")
    assert "<groupId>org.aspose</groupId>" in updated
    assert "<groupId>com.aspose</groupId>" not in updated


# ── T2: Java artifactId change in Maven XML code block ────────────────────

def test_t2_java_artifact_id_replaced_in_code_block(tmp_path):
    """T2: artifactId cells-foss -> aspose-cells-foss replaced inside code block."""
    content = (
        "---\ntitle: Installation\n---\n\n"
        "```xml\n"
        "<dependency>\n"
        "  <groupId>com.aspose</groupId>\n"
        "  <artifactId>cells-foss</artifactId>\n"
        "  <version>1.0.0</version>\n"
        "</dependency>\n"
        "```\n"
    )
    page = _make_content_file(
        tmp_path,
        "content/docs.aspose.org/en/cells/java/getting-started/installation.md",
        content,
    )

    result = sut.migrate_coordinates(page, JAVA_CHANGES, dry_run=False)

    assert result["result"] == sut.R_MIGRATED
    updated = page.read_text(encoding="utf-8")
    assert "<artifactId>aspose-cells-foss</artifactId>" in updated
    assert "<artifactId>cells-foss</artifactId>" not in updated


# ── T3: Python package name change in pip install code block ──────────────

def test_t3_python_package_name_replaced(tmp_path):
    """T3: package_name aspose-old-pkg -> aspose-new-pkg in pip install block."""
    content = (
        "---\ntitle: Installation\n---\n\n"
        "```bash\n"
        "pip install aspose-old-pkg>=25.1\n"
        "```\n"
        "\n"
        "Then import the package:\n\n"
        "```python\n"
        "import aspose_old_pkg\n"
        "```\n"
    )
    page = _make_content_file(
        tmp_path,
        "content/docs.aspose.org/en/myprod/python/getting-started/installation.md",
        content,
    )

    result = sut.migrate_coordinates(page, PYTHON_CHANGES, dry_run=False)

    assert result["result"] in (sut.R_MIGRATED, sut.R_HUMAN_REVIEW)
    assert result["replacements"] >= 1
    updated = page.read_text(encoding="utf-8")
    assert "aspose-new-pkg" in updated
    assert "aspose-old-pkg" not in updated


# ── T4: .NET package name change in dotnet add package code block ─────────

def test_t4_dotnet_package_name_replaced(tmp_path):
    """T4: package_name Aspose.Old.Package -> Aspose.New.Package in dotnet block."""
    content = (
        "---\ntitle: Installation\n---\n\n"
        "```bash\n"
        "dotnet add package Aspose.Old.Package --version 1.0.0\n"
        "```\n"
    )
    page = _make_content_file(
        tmp_path,
        "content/docs.aspose.org/en/myprod/net/getting-started/installation.md",
        content,
    )

    result = sut.migrate_coordinates(page, DOTNET_CHANGES, dry_run=False)

    assert result["result"] in (sut.R_MIGRATED, sut.R_HUMAN_REVIEW)
    assert result["replacements"] >= 1
    updated = page.read_text(encoding="utf-8")
    assert "Aspose.New.Package" in updated
    assert "Aspose.Old.Package" not in updated


# ── T5: Prose mention only -> HUMAN_REVIEW_REQUIRED, 0 replacements ───────

def test_t5_prose_only_mention_human_review(tmp_path):
    """T5: Old coordinate in prose only (no code blocks) -> HUMAN_REVIEW_REQUIRED."""
    content = (
        "---\ntitle: License\n---\n\n"
        "The com.aspose package was previously the only option.\n"
        "Now you can use the new org.aspose coordinates.\n"
    )
    page = _make_content_file(
        tmp_path,
        "content/docs.aspose.org/en/cells/java/getting-started/license.md",
        content,
    )

    result = sut.migrate_coordinates(page, JAVA_CHANGES, dry_run=False)

    # No code blocks to fix -> 0 replacements; prose mention -> HUMAN_REVIEW
    assert result["result"] == sut.R_HUMAN_REVIEW
    assert result["replacements"] == 0
    assert result["prose_mentions"] >= 1
    # Content should be UNCHANGED (only code blocks are auto-fixed)
    assert page.read_text(encoding="utf-8") == content


# ── T6: English-only guard ─────────────────────────────────────────────────

def test_t6_locale_suffixed_file_rejected(tmp_path):
    """T6: Locale-suffixed blog file (index.fr.md) is rejected with SKIPPED_LOCALE.

    blog.aspose.org uses file-suffix-based locale (index.fr.md).
    docs.aspose.org uses directory-based locale (/fr/cells/java/...) — no .fr.md files there.
    """
    content = (
        "---\ntitle: Installation (FR)\n---\n\n"
        "```xml\n"
        "<groupId>com.aspose</groupId>\n"
        "```\n"
    )
    page = _make_content_file(
        tmp_path,
        "content/blog.aspose.org/cells/java/cells-install-guide/index.fr.md",
        content,
    )

    result = sut.migrate_coordinates(
        page, JAVA_CHANGES, dry_run=False, family="cells", platform="java"
    )

    assert result["result"] == sut.R_SKIPPED_LOCALE
    # File must be unchanged
    assert page.read_text(encoding="utf-8") == content


# ── T7: Noop when old coordinate not present ──────────────────────────────

def test_t7_noop_when_old_coordinate_absent(tmp_path):
    """T7: File with no old coordinate values -> NOOP, no writes."""
    content = (
        "---\ntitle: Features\n---\n\n"
        "This page lists the features of the library.\n\n"
        "## Supported formats\n\n- XLSX\n- CSV\n"
    )
    page = _make_content_file(
        tmp_path,
        "content/docs.aspose.org/en/cells/java/developer-guide/features.md",
        content,
    )
    original_mtime = page.stat().st_mtime

    result = sut.migrate_coordinates(page, JAVA_CHANGES, dry_run=False)

    assert result["result"] == sut.R_NOOP
    assert result["replacements"] == 0
    # File must not have been written
    assert page.stat().st_mtime == original_mtime


# ── T8: Code block replacement AND prose mention -> HUMAN_REVIEW ──────────

def test_t8_code_block_replaced_and_prose_flagged(tmp_path):
    """T8: Code block fixed + prose mention flagged -> HUMAN_REVIEW_REQUIRED."""
    content = (
        "---\ntitle: Installation\n---\n\n"
        "The com.aspose group was the original Maven coordinate.\n\n"
        "```xml\n"
        "<dependency>\n"
        "  <groupId>com.aspose</groupId>\n"
        "  <artifactId>cells-foss</artifactId>\n"
        "</dependency>\n"
        "```\n"
    )
    page = _make_content_file(
        tmp_path,
        "content/docs.aspose.org/en/cells/java/getting-started/installation.md",
        content,
    )

    result = sut.migrate_coordinates(page, JAVA_CHANGES, dry_run=False)

    assert result["result"] == sut.R_HUMAN_REVIEW
    assert result["replacements"] >= 1
    assert result["prose_mentions"] >= 1

    updated = page.read_text(encoding="utf-8")
    # Code block must be updated
    assert "<groupId>org.aspose</groupId>" in updated
    # Prose must be UNCHANGED (human review only)
    assert "The com.aspose group was the original Maven coordinate." in updated


# ── run_migration integration test ────────────────────────────────────────

def test_run_migration_uses_manifest_delta(tmp_path):
    """Integration: run_migration reads manifest_delta.json and processes files."""
    # Set up manifest_delta.json
    delta_path = _make_manifest_delta(
        tmp_path, "cells", "java",
        [
            {"old": "com.aspose", "new": "org.aspose", "field": "group_id",
             "change_type": "COORDINATE_CHANGE"},
        ],
    )

    # Create a content file with the old coordinate
    content = (
        "---\ntitle: Quickstart\n---\n\n"
        "```xml\n"
        "<groupId>com.aspose</groupId>\n"
        "```\n"
    )
    _make_content_file(
        tmp_path,
        "content/docs.aspose.org/en/cells/java/getting-started/quickstart.md",
        content,
    )

    summary = sut.run_migration(
        "cells", "java", dry_run=True, manifest_delta_path=delta_path
    )

    assert summary["files_checked"] >= 1
    assert summary["files_migrated"] >= 1
    assert any(c.get("old") == "com.aspose" for c in summary["changes"])


def test_run_migration_no_manifest_delta(tmp_path):
    """run_migration returns NO_MANIFEST_DELTA when delta file is absent."""
    summary = sut.run_migration("cells", "java", dry_run=True)

    assert summary["files_checked"] == 0
    assert any(
        e.get("error") == sut.R_NO_MANIFEST_DELTA
        for e in summary["changes"]
    )
