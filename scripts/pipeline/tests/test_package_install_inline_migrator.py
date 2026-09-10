"""
Tests for commands/content/package_install_inline_migrator.py (ST-054 TC-06,
plans/from_backlog/2026-08-16-st-054-inline-install-command-remediation.md).

The deterministic codemod that replaces an INLINE single-backtick
install-command span with the package-install-inline shortcode (ST-054
TC-01), for the 4 registries package-install.html/package-install-inline.html
cover (pypi, nuget, npm, go_modules). Sibling of
test_package_install_migrator.py -- same fixture/assertion conventions,
scoped to inline spans instead of whole fenced blocks.
"""

import sys
from pathlib import Path

import pytest

_PIPELINE_ROOT = Path(__file__).resolve().parents[1]
if str(_PIPELINE_ROOT) not in sys.path:
    sys.path.insert(0, str(_PIPELINE_ROOT))

import commands.content.package_install_inline_migrator as sut


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

_GO_REGISTRY = {
    "pdf": {"go": {"registry_type": "go_modules",
                    "candidate": {"module_path": "github.com/aspose-pdf-foss/aspose-pdf-foss-for-go"},
                    "verification": {"published": True}}},
}


def test_inline_span_is_replaced_with_shortcode(tmp_path):
    fp = _write(tmp_path, "content/kb.aspose.org/en/slides/net/faq.md", (
        "Run `dotnet add package Aspose.Slides.Foss` to install it.\n"
    ))
    res = sut.migrate_file(fp, "slides", "net", dry_run=False, registry=_NUGET_REGISTRY)
    assert res["result"] == sut.R_MIGRATED
    assert res["inline_replacements"] == 1
    text = fp.read_text(encoding="utf-8")
    assert '{{< package-install-inline "slides" "net" >}}' in text
    assert "dotnet add package" not in text
    assert "`" not in text  # backticks removed, shortcode already emits <code>


def test_install_package_powershell_form_is_replaced(tmp_path):
    """nuget's alternate PowerShell Package Manager Console syntax (ST-054
    TC-02) must also be recognized inline, not just the CLI form."""
    fp = _write(tmp_path, "content/kb.aspose.org/en/slides/net/faq.md", (
        "In the Package Manager Console, run `Install-Package Aspose.Slides.Foss`.\n"
    ))
    res = sut.migrate_file(fp, "slides", "net", dry_run=False, registry=_NUGET_REGISTRY)
    assert res["result"] == sut.R_MIGRATED
    assert res["inline_replacements"] == 1
    text = fp.read_text(encoding="utf-8")
    assert '{{< package-install-inline "slides" "net" >}}' in text


def test_version_flag_tolerated(tmp_path):
    fp = _write(tmp_path, "content/kb.aspose.org/en/slides/net/faq.md", (
        "Run `dotnet add package Aspose.Slides.Foss --version 1.0.0` to install.\n"
    ))
    res = sut.migrate_file(fp, "slides", "net", dry_run=False, registry=_NUGET_REGISTRY)
    assert res["result"] == sut.R_MIGRATED
    assert res["inline_replacements"] == 1


def test_pypi_inline_replacement(tmp_path):
    fp = _write(tmp_path, "content/docs.aspose.org/en/cells/python/getting-started/faq.md", (
        "Install it via `pip install aspose-cells-foss` and you're done.\n"
    ))
    res = sut.migrate_file(fp, "cells", "python", dry_run=False, registry=_PYPI_REGISTRY)
    assert res["result"] == sut.R_MIGRATED
    text = fp.read_text(encoding="utf-8")
    assert '{{< package-install-inline "cells" "python" >}}' in text


def test_go_modules_inline_replacement(tmp_path):
    fp = _write(tmp_path, "content/docs.aspose.org/en/pdf/go/getting-started/faq.md", (
        "Just run `go get github.com/aspose-pdf-foss/aspose-pdf-foss-for-go` in your project.\n"
    ))
    res = sut.migrate_file(fp, "pdf", "go", dry_run=False, registry=_GO_REGISTRY)
    assert res["result"] == sut.R_MIGRATED
    text = fp.read_text(encoding="utf-8")
    assert '{{< package-install-inline "pdf" "go" >}}' in text


def test_span_with_extra_text_beyond_command_not_replaced(tmp_path):
    """A backtick span that CONTAINS the command alongside other words is not
    a fullmatch -- ambiguous prose is left for a human/S-73 pass, mirroring
    package_install_migrator.py's own 'structural safety over aggressive
    matching' posture for its block pass."""
    fp = _write(tmp_path, "content/kb.aspose.org/en/slides/net/faq.md", (
        "Some people write `just run dotnet add package Aspose.Slides.Foss now` "
        "which is not a clean command.\n"
    ))
    res = sut.migrate_file(fp, "slides", "net", dry_run=False, registry=_NUGET_REGISTRY)
    assert res["result"] == sut.R_NOOP
    assert res["inline_replacements"] == 0
    text = fp.read_text(encoding="utf-8")
    assert "dotnet add package" in text  # untouched


def test_text_inside_fenced_block_not_touched_by_this_migrator(tmp_path):
    """Fenced-block content is package_install_migrator.py's own scope --
    this migrator must never touch it, even if a stray single-backtick-shaped
    substring happens to appear inside the fence, so the two migrators can
    run back-to-back with no double-processing."""
    fp = _write(tmp_path, "content/docs.aspose.org/en/slides/net/getting-started/installation.md", (
        "```bash\n"
        "dotnet add package Aspose.Slides.Foss\n"
        "```\n"
    ))
    res = sut.migrate_file(fp, "slides", "net", dry_run=False, registry=_NUGET_REGISTRY)
    assert res["result"] == sut.R_NOOP
    assert res["inline_replacements"] == 0
    text = fp.read_text(encoding="utf-8")
    assert "dotnet add package Aspose.Slides.Foss" in text  # untouched, block migrator's job


def test_package_reference_xml_not_touched(tmp_path):
    """<PackageReference> is raw .csproj XML -- structurally a fenced-block
    artifact, not a natural inline mid-sentence mention. This migrator has no
    pattern for it at all (by design, see module docstring)."""
    fp = _write(tmp_path, "content/docs.aspose.org/en/slides/net/getting-started/faq.md", (
        'Add `<PackageReference Include="Aspose.Slides.Foss" />` to your .csproj.\n'
    ))
    res = sut.migrate_file(fp, "slides", "net", dry_run=False, registry=_NUGET_REGISTRY)
    assert res["result"] == sut.R_NOOP
    assert res["inline_replacements"] == 0


def test_troubleshooting_heading_not_touched(tmp_path):
    """Regression pin (real live bug found this session, 2026-09-10): a
    heading like '### `dotnet add package X` cannot find the package'
    (content/kb.aspose.org/en/words/net/troubleshooting.md, both markdown-
    heading and frontmatter heading: field forms) explains the command
    DOESN'T work -- not an install instruction. The first version of this
    migrator had no heading guard and would have replaced it with the live
    shortcode, producing a self-contradicting heading once the package
    actually publishes. Must reuse package_install_literal.py's own
    _is_noise_line() guard, never re-derive a second copy of this logic."""
    fp = _write(tmp_path, "content/kb.aspose.org/en/words/net/troubleshooting.md", (
        "---\n"
        "faq:\n"
        "  - heading: '`dotnet add package Aspose.Words.FOSS` cannot find the package'\n"
        "---\n\n"
        "### `dotnet add package Aspose.Words.FOSS` cannot find the package\n\n"
        "A NuGet package has not been published yet for this FOSS edition.\n"
    ))
    registry = {"words": {"net": {"registry_type": "nuget", "candidate": {"name": "Aspose.Words.FOSS"},
                                    "verification": {"published": False}}}}
    res = sut.migrate_file(fp, "words", "net", dry_run=False, registry=registry)
    assert res["result"] == sut.R_NOOP
    assert res["inline_replacements"] == 0
    text = fp.read_text(encoding="utf-8")
    assert "dotnet add package Aspose.Words.FOSS" in text  # untouched in both places
    assert "package-install-inline" not in text


def test_body_text_repeating_the_same_command_outside_a_heading_is_still_migrated(tmp_path):
    """The heading guard must not become a blanket bypass for the whole file
    -- the same command as plain prose (not a heading) elsewhere is still a
    normal inline mention and gets migrated."""
    fp = _write(tmp_path, "content/kb.aspose.org/en/words/net/troubleshooting.md", (
        "### Some other heading\n\n"
        "Just run `dotnet add package Aspose.Words.FOSS` to install it.\n"
    ))
    res = sut.migrate_file(fp, "words", "net", dry_run=False, registry=_NUGET_REGISTRY_WORDS)
    assert res["result"] == sut.R_MIGRATED
    assert res["inline_replacements"] == 1


_NUGET_REGISTRY_WORDS = {
    "words": {"net": {"registry_type": "nuget", "candidate": {"name": "Aspose.Words.FOSS"},
                        "verification": {"published": True}}},
}


def test_multiple_inline_spans_all_replaced(tmp_path):
    fp = _write(tmp_path, "content/kb.aspose.org/en/slides/net/faq.md", (
        "On Windows: `dotnet add package Aspose.Slides.Foss`.\n"
        "Or via PMC: `Install-Package Aspose.Slides.Foss`.\n"
    ))
    res = sut.migrate_file(fp, "slides", "net", dry_run=False, registry=_NUGET_REGISTRY)
    assert res["result"] == sut.R_MIGRATED
    assert res["inline_replacements"] == 2
    text = fp.read_text(encoding="utf-8")
    assert text.count('{{< package-install-inline "slides" "net" >}}') == 2


def test_dry_run_does_not_write(tmp_path):
    fp = _write(tmp_path, "content/kb.aspose.org/en/slides/net/faq.md", (
        "Run `dotnet add package Aspose.Slides.Foss`.\n"
    ))
    original = fp.read_text(encoding="utf-8")
    res = sut.migrate_file(fp, "slides", "net", dry_run=True, registry=_NUGET_REGISTRY)
    assert res["result"] == sut.R_DRY_RUN
    assert res["inline_replacements"] == 1
    assert fp.read_text(encoding="utf-8") == original


def test_no_registry_entry_is_noop(tmp_path):
    fp = _write(tmp_path, "content/docs.aspose.org/en/words/net/getting-started/faq.md", (
        "Run `dotnet add package Aspose.Words.FOSS`.\n"
    ))
    res = sut.migrate_file(fp, "words", "net", dry_run=False, registry=_NUGET_REGISTRY)
    assert res["result"] == sut.R_NO_REGISTRY_ENTRY


def test_maven_registry_type_is_noop_not_migrated_by_this_module(tmp_path):
    fp = _write(tmp_path, "content/docs.aspose.org/en/cells/java/getting-started/faq.md", (
        "Run `pip install aspose-cells-foss`.\n"
    ))
    registry = {"cells": {"java": {"registry_type": "maven", "candidate": {}, "verification": {"published": True}}}}
    res = sut.migrate_file(fp, "cells", "java", dry_run=False, registry=registry)
    assert res["result"] == sut.R_NO_REGISTRY_ENTRY


def test_discover_files_english_only_excludes_locale_dirs_and_suffixes(tmp_path):
    """English-only: locale directories (docs/kb/products) and locale-suffixed
    filenames (blog) are both excluded -- ST-054 TC-07's scope, not TC-06's."""
    _write(tmp_path, "content/docs.aspose.org/en/slides/net/getting-started/faq.md", "en doc")
    _write(tmp_path, "content/docs.aspose.org/fr/slides/net/getting-started/faq.md", "fr doc")
    _write(tmp_path, "content/kb.aspose.org/en/slides/net/faq.md", "en kb")
    _write(tmp_path, "content/kb.aspose.org/de/slides/net/faq.md", "de kb")
    _write(tmp_path, "content/blog.aspose.org/slides/net/some-post/index.md", "en blog")
    _write(tmp_path, "content/blog.aspose.org/slides/net/some-post/index.fr.md", "fr blog")
    _write(tmp_path, "content/products.aspose.org/en/slides/net/_index.md", "en products")
    _write(tmp_path, "content/reference.aspose.org/en/slides/net/Presentation.md", "ref -- excluded")

    files = sut.discover_files_english_only("slides", "net")
    rels = {str(f.relative_to(tmp_path)).replace("\\", "/") for f in files}
    assert "content/docs.aspose.org/en/slides/net/getting-started/faq.md" in rels
    assert "content/kb.aspose.org/en/slides/net/faq.md" in rels
    assert "content/blog.aspose.org/slides/net/some-post/index.md" in rels
    assert "content/products.aspose.org/en/slides/net/_index.md" in rels
    assert "content/docs.aspose.org/fr/slides/net/getting-started/faq.md" not in rels
    assert "content/kb.aspose.org/de/slides/net/faq.md" not in rels
    assert "content/blog.aspose.org/slides/net/some-post/index.fr.md" not in rels
    assert not any("reference.aspose.org" in r for r in rels)


def test_run_migration_summary_aggregates_across_files(tmp_path):
    _write(tmp_path, "content/kb.aspose.org/en/slides/net/faq.md", (
        "Run `dotnet add package Aspose.Slides.Foss`.\n"
    ))
    _write(tmp_path, "content/docs.aspose.org/en/slides/net/getting-started/other.md", (
        "Or `Install-Package Aspose.Slides.Foss` via PMC.\n"
    ))
    summary = sut.run_migration("slides", "net", dry_run=True, registry=_NUGET_REGISTRY)
    assert summary["files_checked"] == 2
    assert summary["files_migrated"] == 2
    assert summary["inline_replacements"] == 2


class TestCollisionGate:
    """PKGINSTALL-COLLISION-CLASSIFIER: mirrors test_package_install_migrator.py's
    own TestCollisionGate -- same real cells/net structural-collision proof,
    same --force/respect_collision_gate escape hatches."""

    _CELLS_NET_REGISTRY = {
        "cells": {"net": {"registry_type": "nuget", "candidate": {"name": "Aspose.Cells.FOSS"}}},
    }

    def test_collision_risk_product_blocks_by_default(self, tmp_path):
        _write(tmp_path, "content/kb.aspose.org/en/cells/net/faq.md", (
            "Run `dotnet add package Aspose.Cells.FOSS`.\n"
        ))
        summary = sut.run_migration("cells", "net", dry_run=True, registry=self._CELLS_NET_REGISTRY)
        assert summary["collision_gate_blocked"] is True
        assert summary["collision_classification"] == "COLLISION_RISK_STRUCTURAL"
        assert summary["files_checked"] == 0
        assert summary["inline_replacements"] == 0

    def test_force_bypasses_the_gate(self, tmp_path):
        _write(tmp_path, "content/kb.aspose.org/en/cells/net/faq.md", (
            "Run `dotnet add package Aspose.Cells.FOSS`.\n"
        ))
        summary = sut.run_migration(
            "cells", "net", dry_run=True, registry=self._CELLS_NET_REGISTRY, force=True,
        )
        assert summary["collision_gate_blocked"] is False
        assert summary["files_checked"] == 1
        assert summary["inline_replacements"] == 1

    def test_safe_product_is_never_blocked(self, tmp_path):
        _write(tmp_path, "content/kb.aspose.org/en/slides/net/faq.md", (
            "Run `dotnet add package Aspose.Slides.Foss`.\n"
        ))
        summary = sut.run_migration("slides", "net", dry_run=True, registry=_NUGET_REGISTRY)
        assert summary["collision_gate_blocked"] is False
        assert summary["collision_classification"] == "SAFE_FOR_MECHANICAL_MIGRATION"
