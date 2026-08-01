"""
Tests for commands/content/package_install_migrator.py (Mission
MT015-2026-07-30-PACKAGE-REGISTRY, TC-MT015-09).

The deterministic codemod that replaces a sole-command fenced install block
with the package-install shortcode, for the 4 registries package-install.html
covers (pypi, nuget, npm, go_modules). Mirrors maven_shortcode_migrator.py's
structure and test conventions (Mission MT008) but is scoped to whole-block
replacement only -- inline backtick mentions are counted, never rewritten
(see module docstring for why).
"""

import sys
from pathlib import Path

import pytest

_PIPELINE_ROOT = Path(__file__).resolve().parents[1]
if str(_PIPELINE_ROOT) not in sys.path:
    sys.path.insert(0, str(_PIPELINE_ROOT))

import commands.content.package_install_migrator as sut


@pytest.fixture(autouse=True)
def isolate_repo(tmp_path):
    sut.configure(repo_root=tmp_path)
    yield
    sut.configure(repo_root=None)


def _write(tmp_path: Path, rel_path: str, content: str) -> Path:
    p = tmp_path / rel_path
    p.parent.mkdir(parents=True, exist_ok=True)
    p.write_text(content, encoding="utf-8")
    return p


_NUGET_REGISTRY = {
    "slides": {"net": {"registry_type": "nuget", "candidate": {"name": "Aspose.Slides.Foss"},
                        "verification": {"published": False}}},
}

_PYPI_REGISTRY = {
    "cells": {"python": {"registry_type": "pypi", "candidate": {"name": "aspose-cells-foss"},
                          "verification": {"published": True}}},
}


def test_block_pass_replaces_sole_command_fenced_block(tmp_path):
    fp = _write(tmp_path, "content/docs.aspose.org/en/slides/net/getting-started/installation.md", (
        "## Installation\n\n"
        "```bash\n"
        "dotnet add package Aspose.Slides.Foss\n"
        "```\n\n"
        "Then verify.\n"
    ))
    res = sut.migrate_file(fp, "slides", "net", dry_run=False, registry=_NUGET_REGISTRY)
    assert res["result"] == sut.R_MIGRATED
    assert res["block_replacements"] == 1
    text = fp.read_text(encoding="utf-8")
    assert '{{< package-install "slides" "net" >}}' in text
    assert "dotnet add package" not in text
    assert "```bash" not in text  # whole fence removed


def test_multi_line_block_not_migrated_as_sole_command(tmp_path):
    """A fenced block with the command PLUS other steps is not a sole-command
    block -- migrating it would silently drop the other lines. Structural
    safety over aggressive matching."""
    fp = _write(tmp_path, "content/docs.aspose.org/en/slides/net/getting-started/installation.md", (
        "```bash\n"
        "git clone https://example.com/repo.git\n"
        "dotnet add package Aspose.Slides.Foss\n"
        "```\n"
    ))
    res = sut.migrate_file(fp, "slides", "net", dry_run=False, registry=_NUGET_REGISTRY)
    assert res["result"] == sut.R_NOOP
    assert res["block_replacements"] == 0
    text = fp.read_text(encoding="utf-8")
    assert "dotnet add package" in text  # untouched


def test_inline_mention_counted_not_rewritten(tmp_path):
    """Inline backtick mentions in prose are reported but never auto-migrated
    -- package-install renders a block-level element, unsafe to splice
    mid-sentence."""
    fp = _write(tmp_path, "content/kb.aspose.org/en/slides/net/faq.md", (
        "#### How do I install it?\n\n"
        "Run `dotnet add package Aspose.Slides.Foss`. Requires .NET 9.0.\n"
    ))
    res = sut.migrate_file(fp, "slides", "net", dry_run=False, registry=_NUGET_REGISTRY)
    assert res["result"] == sut.R_NOOP
    assert res["block_replacements"] == 0
    assert res["inline_mentions_found"] == 1
    text = fp.read_text(encoding="utf-8")
    assert "dotnet add package Aspose.Slides.Foss" in text  # untouched, not mangled


def test_dry_run_does_not_write(tmp_path):
    fp = _write(tmp_path, "content/docs.aspose.org/en/slides/net/getting-started/installation.md", (
        "```bash\ndotnet add package Aspose.Slides.Foss\n```\n"
    ))
    original = fp.read_text(encoding="utf-8")
    res = sut.migrate_file(fp, "slides", "net", dry_run=True, registry=_NUGET_REGISTRY)
    assert res["result"] == sut.R_DRY_RUN
    assert res["block_replacements"] == 1
    assert fp.read_text(encoding="utf-8") == original


def test_no_registry_entry_is_noop(tmp_path):
    fp = _write(tmp_path, "content/docs.aspose.org/en/words/net/getting-started/installation.md", (
        "```bash\ndotnet add package Aspose.Words.FOSS\n```\n"
    ))
    res = sut.migrate_file(fp, "words", "net", dry_run=False, registry=_NUGET_REGISTRY)
    assert res["result"] == sut.R_NO_REGISTRY_ENTRY


def test_maven_registry_type_is_noop_not_migrated_by_this_module(tmp_path):
    """Maven/Cargo keep their own dedicated shortcode/migrator -- this module
    must never touch a family/platform with those registry_types."""
    fp = _write(tmp_path, "content/docs.aspose.org/en/cells/java/getting-started/installation.md", (
        "```bash\npip install aspose-cells-foss\n```\n"
    ))
    registry = {"cells": {"java": {"registry_type": "maven", "candidate": {}, "verification": {"published": True}}}}
    res = sut.migrate_file(fp, "cells", "java", dry_run=False, registry=registry)
    assert res["result"] == sut.R_NO_REGISTRY_ENTRY


def test_pypi_block_replacement(tmp_path):
    fp = _write(tmp_path, "content/products.aspose.org/en/cells/python/_index.md", (
        "```bash\npip install aspose-cells-foss\n```\n"
    ))
    res = sut.migrate_file(fp, "cells", "python", dry_run=False, registry=_PYPI_REGISTRY)
    assert res["result"] == sut.R_MIGRATED
    text = fp.read_text(encoding="utf-8")
    assert '{{< package-install "cells" "python" >}}' in text


def test_discover_files_covers_docs_kb_blog_products_all_locales(tmp_path):
    _write(tmp_path, "content/docs.aspose.org/en/slides/net/getting-started/installation.md", "en doc")
    _write(tmp_path, "content/docs.aspose.org/fr/slides/net/getting-started/installation.md", "fr doc")
    _write(tmp_path, "content/kb.aspose.org/en/slides/net/faq.md", "en kb")
    _write(tmp_path, "content/blog.aspose.org/slides/net/some-post/index.md", "en blog")
    _write(tmp_path, "content/products.aspose.org/en/slides/net/_index.md", "en products")
    _write(tmp_path, "content/reference.aspose.org/en/slides/net/Presentation.md", "ref -- excluded")

    files = sut.discover_files("slides", "net")
    rels = {str(f.relative_to(tmp_path)).replace("\\", "/") for f in files}
    assert "content/docs.aspose.org/en/slides/net/getting-started/installation.md" in rels
    assert "content/docs.aspose.org/fr/slides/net/getting-started/installation.md" in rels
    assert "content/kb.aspose.org/en/slides/net/faq.md" in rels
    assert "content/blog.aspose.org/slides/net/some-post/index.md" in rels
    assert "content/products.aspose.org/en/slides/net/_index.md" in rels
    assert not any("reference.aspose.org" in r for r in rels)


def test_run_migration_summary_aggregates_across_files(tmp_path):
    _write(tmp_path, "content/docs.aspose.org/en/slides/net/getting-started/installation.md", (
        "```bash\ndotnet add package Aspose.Slides.Foss\n```\n"
    ))
    _write(tmp_path, "content/kb.aspose.org/en/slides/net/faq.md", (
        "Run `dotnet add package Aspose.Slides.Foss`.\n"
    ))
    summary = sut.run_migration("slides", "net", dry_run=True, registry=_NUGET_REGISTRY)
    assert summary["files_checked"] == 2
    assert summary["files_migrated"] == 1
    assert summary["block_replacements"] == 1
    assert summary["inline_mentions_found"] == 1
