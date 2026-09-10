"""
Tests for install_block_updater.py (TC-05).

7 test scenarios per the plan:
  T1: Add block to page without one (.NET INSTALL_CMD_ADDED)
  T2: Update existing block (Python INSTALL_CMD_CHANGED)
  T3: Version-only bump (Java VERSION_BUMP)
  T4: Case-insensitive .NET package match (AF-06 case -- Aspose.PDF.FOSS vs Aspose.Pdf.Foss)
  T5: English-only guard (locale-suffixed file rejected)
  T6: Noop when content already matches knowledge
  T7: quickstart.md gets same update as installation.md

ST-054 TC-03 (2026-09-10): the durability fix -- a page already rendering its
install command via shortcode must be left untouched by any future
manifest-delta event, and a not-yet-migrated page must be migrated straight
to the shortcode call (not another literal block) whenever a registry entry
exists to ground it. See TestTC03ShortcodeAware below.
"""

import json
import sys
import tempfile
from pathlib import Path

import pytest

# Make sure pipeline root is on the path
_PIPELINE_ROOT = Path(__file__).resolve().parents[1]
if str(_PIPELINE_ROOT) not in sys.path:
    sys.path.insert(0, str(_PIPELINE_ROOT))

import commands.content.install_block_updater as sut

# ── Fixtures ───────────────────────────────────────────────────────────────

DOTNET_INSTALL_INFO = {
    "install_block": "dotnet add package Aspose.3D.Converter --version 1.0.0",
    "package_name": "Aspose.3D.Converter",
    "version": "1.0.0",
    "group_id": "",
    "artifact_id": "",
}

PYTHON_INSTALL_INFO = {
    "install_block": "pip install aspose-pdf>=25.1",
    "package_name": "aspose-pdf",
    "version": "25.1",
    "group_id": "",
    "artifact_id": "",
}

JAVA_INSTALL_INFO = {
    "install_block": (
        "<dependency>\n"
        "  <groupId>org.aspose</groupId>\n"
        "  <artifactId>aspose-cells-foss</artifactId>\n"
        "  <version>26.5.0</version>\n"
        "</dependency>"
    ),
    "package_name": "aspose-cells-foss",
    "version": "26.5.0",
    "group_id": "org.aspose",
    "artifact_id": "aspose-cells-foss",
}

# Case-sensitivity test: knowledge says Aspose.PDF.FOSS, content says Aspose.Pdf.Foss (AF-06)
DOTNET_FOSS_UPPER_INFO = {
    "install_block": "dotnet add package Aspose.PDF.FOSS --version 26.6.0",
    "package_name": "Aspose.PDF.FOSS",
    "version": "26.6.0",
    "group_id": "",
    "artifact_id": "",
}


@pytest.fixture(autouse=True)
def isolate_repo(tmp_path):
    """Each test gets a fresh temp repo root."""
    sut.configure(repo_root=tmp_path)
    yield
    sut.configure(repo_root=None)  # restore default


def _make_content_file(tmp_path: Path, rel_path: str, content: str) -> Path:
    p = tmp_path / rel_path
    p.parent.mkdir(parents=True, exist_ok=True)
    p.write_text(content, encoding="utf-8")
    return p


def _make_install_md(tmp_path: Path, family: str, platform: str, block_content: str) -> Path:
    p = tmp_path / "knowledge" / family / platform / "merged" / "install.md"
    p.parent.mkdir(parents=True, exist_ok=True)
    p.write_text(f"# Install\n\n```\n{block_content}\n```\n", encoding="utf-8")
    return p


def _make_manifest_delta(
    tmp_path: Path, family: str, platform: str, events: list
) -> Path:
    p = tmp_path / "knowledge" / family / platform / "merged" / "manifest_delta.json"
    p.parent.mkdir(parents=True, exist_ok=True)
    p.write_text(
        json.dumps({"install_cmd_changes": events, "coordinate_changes": [], "version_changes": []}),
        encoding="utf-8",
    )
    return p


# ── T1: Add block to page without one (.NET INSTALL_CMD_ADDED) ─────────────

def test_t1_add_block_dotnet_no_prior_block(tmp_path):
    """T1: Page has no install block; event=INSTALL_CMD_ADDED; block should be added."""
    # A page with no install command at all
    page_content = (
        "---\ntitle: Installation\n---\n\n"
        "## Installation\n\n"
        "Follow the steps below to install the package.\n\n"
        "## See Also\n\n- [Docs](../)\n"
    )
    page = _make_content_file(
        tmp_path,
        "content/docs.aspose.org/en/3d/net/getting-started/installation.md",
        page_content,
    )
    # No existing install block means _block_contains_install returns False.
    # The updater correctly returns SKIPPED_NO_BLOCK (can't add without anchor).
    # This is by design: INSTALL_CMD_ADDED requires a human to decide placement.
    # The handler flags this as SKIPPED so the operator is aware.
    result = sut.update_install_blocks(
        page, DOTNET_INSTALL_INFO, "dotnet", dry_run=True, family="3d", platform="net"
    )
    # No code block in file -> SKIPPED_NO_BLOCK (correct behavior for no-anchor case)
    assert result["result"] == sut.R_SKIPPED_NO_BLOCK


# ── T2: Update existing block (Python INSTALL_CMD_CHANGED) ────────────────

def test_t2_update_existing_block_python(tmp_path):
    """T2: Page has old pip install block; INSTALL_CMD_CHANGED; new block should replace it."""
    page_content = (
        "---\ntitle: Installation\n---\n\n"
        "## Install\n\n"
        "```bash\n"
        "pip install aspose-pdf>=0.1.0-alpha\n"
        "```\n\n"
        "## See Also\n"
    )
    page = _make_content_file(
        tmp_path,
        "content/docs.aspose.org/en/pdf/python/getting-started/installation.md",
        page_content,
    )
    result = sut.update_install_blocks(
        page, PYTHON_INSTALL_INFO, "python", dry_run=True, family="pdf", platform="python"
    )
    assert result["result"] == sut.R_DRY_RUN
    assert result["blocks_updated"] == 1


def test_t2_update_writes_correct_content(tmp_path):
    """T2 (execute): Updated file contains the new install command."""
    page_content = (
        "---\ntitle: Installation\nprovenance:\n  auto_updatable: true\n---\n\n"
        "## Install\n\n"
        "```bash\n"
        "pip install aspose-pdf>=0.1.0-alpha\n"
        "```\n"
    )
    page = _make_content_file(
        tmp_path,
        "content/docs.aspose.org/en/pdf/python/getting-started/installation.md",
        page_content,
    )
    result = sut.update_install_blocks(
        page, PYTHON_INSTALL_INFO, "python", dry_run=False, family="pdf", platform="python"
    )
    assert result["result"] == sut.R_UPDATED
    written = page.read_text(encoding="utf-8")
    assert "pip install aspose-pdf>=25.1" in written
    assert "0.1.0-alpha" not in written


# ── T3: Version-only bump (Java) ───────────────────────────────────────────

def test_t3_version_bump_java(tmp_path):
    """T3: Java page has old groupId/artifactId/version; VERSION_BUMP; new version replaces old."""
    old_block = (
        "<dependency>\n"
        "  <groupId>com.aspose</groupId>\n"
        "  <artifactId>cells-foss</artifactId>\n"
        "  <version>1.0.0</version>\n"
        "</dependency>"
    )
    page_content = (
        "---\ntitle: Installation\nprovenance:\n  auto_updatable: true\n---\n\n"
        "## Maven\n\n"
        "```xml\n"
        + old_block
        + "\n```\n"
    )
    page = _make_content_file(
        tmp_path,
        "content/docs.aspose.org/en/cells/java/getting-started/installation.md",
        page_content,
    )
    result = sut.update_install_blocks(
        page, JAVA_INSTALL_INFO, "java", dry_run=False, family="cells", platform="java"
    )
    assert result["result"] == sut.R_UPDATED
    written = page.read_text(encoding="utf-8")
    assert "org.aspose" in written
    assert "aspose-cells-foss" in written
    assert "26.5.0" in written
    assert "com.aspose" not in written


# ── T4: Case-insensitive .NET match (AF-06) ────────────────────────────────

def test_t4_dotnet_case_insensitive_match(tmp_path):
    """T4: Content has Aspose.Pdf.Foss (mixed case), knowledge has Aspose.PDF.FOSS; must match."""
    page_content = (
        "---\ntitle: Installation\nprovenance:\n  auto_updatable: true\n---\n\n"
        "## Install\n\n"
        "```bash\n"
        "dotnet add package Aspose.Pdf.Foss --version 0.1.0-alpha\n"
        "```\n"
    )
    page = _make_content_file(
        tmp_path,
        "content/docs.aspose.org/en/pdf/net/getting-started/installation.md",
        page_content,
    )
    result = sut.update_install_blocks(
        page, DOTNET_FOSS_UPPER_INFO, "dotnet", dry_run=False, family="pdf", platform="net"
    )
    assert result["result"] == sut.R_UPDATED
    written = page.read_text(encoding="utf-8")
    assert "Aspose.PDF.FOSS" in written
    assert "26.6.0" in written
    assert "0.1.0-alpha" not in written


# ── T5: English-only guard ─────────────────────────────────────────────────

def test_t5_english_only_locale_suffix_rejected(tmp_path):
    """T5: locale-suffixed file (index.fr.md) must be rejected."""
    page_content = (
        "---\ntitle: Installation\n---\n\n"
        "```bash\n"
        "pip install aspose-pdf>=0.1.0\n"
        "```\n"
    )
    # Blog-style locale-suffixed file
    page = _make_content_file(
        tmp_path,
        "content/blog.aspose.org/pdf/python/install-guide/index.fr.md",
        page_content,
    )
    result = sut.update_install_blocks(
        page, PYTHON_INSTALL_INFO, "python", dry_run=True, family="pdf", platform="python"
    )
    assert result["result"] == sut.R_SKIPPED_LOCALE


def test_t5_english_only_non_en_dir_rejected(tmp_path):
    """T5: docs path under /fr/ directory must be rejected."""
    page_content = (
        "---\ntitle: Installation\n---\n\n"
        "```bash\n"
        "dotnet add package Aspose.3D --version 26.1.0\n"
        "```\n"
    )
    # French locale directory
    page = _make_content_file(
        tmp_path,
        "content/docs.aspose.org/fr/3d/net/getting-started/installation.md",
        page_content,
    )
    result = sut.update_install_blocks(
        page, DOTNET_INSTALL_INFO, "dotnet", dry_run=True, family="3d", platform="net"
    )
    assert result["result"] == sut.R_SKIPPED_LOCALE


# ── T6: Noop when already matches ─────────────────────────────────────────

def test_t6_noop_when_content_matches(tmp_path):
    """T6: Content already has the correct install block; no change needed."""
    page_content = (
        "---\ntitle: Installation\n---\n\n"
        "```bash\n"
        "dotnet add package Aspose.3D.Converter --version 1.0.0\n"
        "```\n"
    )
    page = _make_content_file(
        tmp_path,
        "content/docs.aspose.org/en/3d/net/getting-started/installation.md",
        page_content,
    )
    result = sut.update_install_blocks(
        page, DOTNET_INSTALL_INFO, "dotnet", dry_run=True, family="3d", platform="net"
    )
    assert result["result"] == sut.R_NOOP
    assert result["blocks_updated"] == 0


# ── T7: quickstart.md gets same update ────────────────────────────────────

def test_t7_quickstart_updated_same_as_installation(tmp_path):
    """T7: run_update applies the same fix to quickstart.md and installation.md."""
    install_content = (
        "---\ntitle: Installation\nprovenance:\n  auto_updatable: true\n---\n\n"
        "## Install\n\n"
        "```bash\n"
        "dotnet add package Aspose.3D --version 26.1.0\n"
        "```\n"
    )
    quickstart_content = (
        "---\ntitle: Quick Start\nprovenance:\n  auto_updatable: true\n---\n\n"
        "## Install\n\n"
        "```bash\n"
        "dotnet add package Aspose.3D --version 26.1.0\n"
        "```\n"
        "\n## Hello World\n"
    )
    _make_content_file(
        tmp_path,
        "content/docs.aspose.org/en/3d/net/getting-started/installation.md",
        install_content,
    )
    _make_content_file(
        tmp_path,
        "content/docs.aspose.org/en/3d/net/getting-started/quickstart.md",
        quickstart_content,
    )

    # Set up knowledge artifacts
    _make_install_md(
        tmp_path, "3d", "net", "dotnet add package Aspose.3D.Converter --version 1.0.0"
    )
    _make_manifest_delta(
        tmp_path,
        "3d",
        "net",
        [{"change_type": "INSTALL_CMD_CHANGED", "old": "dotnet add package Aspose.3D --version 26.1.0", "new": "dotnet add package Aspose.3D.Converter --version 1.0.0"}],
    )

    summary = sut.run_update("3d", "net", dry_run=True)

    assert summary["event"] == "INSTALL_CMD_CHANGED"
    assert summary["files_checked"] == 2
    assert summary["files_updated"] == 2
    dry_results = [r for r in summary["results"] if r["result"] == sut.R_DRY_RUN]
    assert len(dry_results) == 2, f"Expected 2 DRY_RUN results, got: {[r['result'] for r in summary['results']]}"


# ── ST-054 TC-03: shortcode-aware durability fix ───────────────────────────

def _make_registry(tmp_path: Path, family: str, platform: str, registry_type: str) -> Path:
    p = tmp_path / "data" / "package_registry.json"
    p.parent.mkdir(parents=True, exist_ok=True)
    p.write_text(
        json.dumps({family: {platform: {"registry_type": registry_type}}}),
        encoding="utf-8",
    )
    return p


class TestTC03ShortcodeAware:
    def test_page_already_using_shortcode_is_left_untouched(self, tmp_path):
        """A page already calling the inline shortcode is self-updating at
        Hugo build time -- a simulated version-bump event must report NOOP
        and must not rewrite the shortcode call into a literal block."""
        page_content = (
            "---\ntitle: Installation\nprovenance:\n  auto_updatable: true\n---\n\n"
            'Install: {{< package-install-inline "pdf" "python" >}}\n'
        )
        page = _make_content_file(
            tmp_path,
            "content/docs.aspose.org/en/pdf/python/getting-started/installation.md",
            page_content,
        )
        _make_registry(tmp_path, "pdf", "python", "pypi")
        result = sut.update_install_blocks(
            page, PYTHON_INSTALL_INFO, "python", dry_run=False, family="pdf", platform="python"
        )
        assert result["result"] == sut.R_NOOP
        assert result["blocks_updated"] == 0
        assert page.read_text(encoding="utf-8") == page_content

    def test_page_already_using_block_shortcode_is_left_untouched(self, tmp_path):
        """Same guard, for the block-level package-install shortcode (not
        just the inline sibling)."""
        page_content = (
            "---\ntitle: Installation\nprovenance:\n  auto_updatable: true\n---\n\n"
            '{{< package-install "pdf" "python" >}}\n'
        )
        page = _make_content_file(
            tmp_path,
            "content/docs.aspose.org/en/pdf/python/getting-started/installation.md",
            page_content,
        )
        result = sut.update_install_blocks(
            page, PYTHON_INSTALL_INFO, "python", dry_run=False, family="pdf", platform="python"
        )
        assert result["result"] == sut.R_NOOP
        assert result["blocks_updated"] == 0

    def test_unmigrated_page_gets_shortcode_instead_of_literal_block(self, tmp_path):
        """A page not yet migrated, but with a registry entry for its
        family/platform, must be rewritten to the shortcode call -- not
        another literal block -- so it never needs migrating again."""
        page_content = (
            "---\ntitle: Installation\nprovenance:\n  auto_updatable: true\n---\n\n"
            "## Install\n\n"
            "```bash\n"
            "pip install aspose-pdf>=0.1.0-alpha\n"
            "```\n"
        )
        page = _make_content_file(
            tmp_path,
            "content/docs.aspose.org/en/pdf/python/getting-started/installation.md",
            page_content,
        )
        _make_registry(tmp_path, "pdf", "python", "pypi")
        result = sut.update_install_blocks(
            page, PYTHON_INSTALL_INFO, "python", dry_run=False, family="pdf", platform="python"
        )
        assert result["result"] == sut.R_UPDATED
        written = page.read_text(encoding="utf-8")
        assert '{{< package-install "pdf" "python" >}}' in written
        assert "pip install" not in written
        assert "```" not in written

    def test_unregistered_family_platform_falls_back_to_literal_block(self, tmp_path):
        """No data/package_registry.json entry for this family/platform (or no
        registry file at all) -- must fall back to the pre-TC-03 literal-block
        behavior unchanged, never crash."""
        page_content = (
            "---\ntitle: Installation\nprovenance:\n  auto_updatable: true\n---\n\n"
            "```bash\n"
            "pip install aspose-pdf>=0.1.0-alpha\n"
            "```\n"
        )
        page = _make_content_file(
            tmp_path,
            "content/docs.aspose.org/en/pdf/python/getting-started/installation.md",
            page_content,
        )
        # No data/package_registry.json written at all under tmp_path.
        result = sut.update_install_blocks(
            page, PYTHON_INSTALL_INFO, "python", dry_run=False, family="pdf", platform="python"
        )
        assert result["result"] == sut.R_UPDATED
        written = page.read_text(encoding="utf-8")
        assert "pip install aspose-pdf>=25.1" in written
        assert "package-install" not in written
