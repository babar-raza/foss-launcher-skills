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


def test_sole_command_with_version_flag_is_migrated(tmp_path):
    """Found live 2026-08-02 (MT018 verification pass): dotnet's CLI syntax
    for a version pin is space-separated (`--version X`), unlike npm's `@X`
    or pip's `==X` which glue onto the package token with no space -- the
    original regex only ever captured one \\S+ token, so `--version 1.0.0`
    trailing content caused _block_is_sole_command's fullmatch to fail and
    the block was left as a false "unfixable inline mention". This is a real,
    safe, isolated code block -- just with a version pin -- and must migrate."""
    fp = _write(tmp_path, "content/docs.aspose.org/en/slides/net/getting-started/installation.md", (
        "```bash\n"
        "dotnet add package Aspose.Slides.Foss --version 1.0.0\n"
        "```\n"
    ))
    res = sut.migrate_file(fp, "slides", "net", dry_run=False, registry=_NUGET_REGISTRY)
    assert res["result"] == sut.R_MIGRATED
    assert res["block_replacements"] == 1
    text = fp.read_text(encoding="utf-8")
    assert '{{< package-install "slides" "net" >}}' in text
    assert "--version" not in text


def test_pypi_sole_command_with_version_pin_is_migrated(tmp_path):
    """pip's version pin glues onto the package token (no space) -- already
    covered by the original \\S+ token match, confirmed still working after
    the --version-flag extension (regression pin, not a new capability)."""
    fp = _write(tmp_path, "content/docs.aspose.org/en/cells/python/getting-started/installation.md", (
        "```bash\n"
        "pip install aspose-cells-foss==26.3.2\n"
        "```\n"
    ))
    res = sut.migrate_file(fp, "cells", "python", dry_run=False, registry=_PYPI_REGISTRY)
    assert res["result"] == sut.R_MIGRATED
    assert res["block_replacements"] == 1


def test_sole_command_with_extra_flags_beyond_version_still_not_migrated(tmp_path):
    """Confirms the --version tolerance is narrowly scoped, not a blanket
    'anything after the package name is fine' loosening -- a block with
    additional unrelated flags is still correctly treated as a multi-part
    command, not a safe sole-command replacement."""
    fp = _write(tmp_path, "content/docs.aspose.org/en/slides/net/getting-started/installation.md", (
        "```bash\n"
        "dotnet add package Aspose.Slides.Foss --version 1.0.0 --prerelease\n"
        "```\n"
    ))
    res = sut.migrate_file(fp, "slides", "net", dry_run=False, registry=_NUGET_REGISTRY)
    assert res["result"] == sut.R_NOOP
    assert res["block_replacements"] == 0
    text = fp.read_text(encoding="utf-8")
    assert "--prerelease" in text  # untouched


def test_inline_mention_with_version_flag_still_counted_once(tmp_path):
    """The extended pattern must not double-count or miscount an inline
    (non-block) mention that happens to include a --version flag."""
    fp = _write(tmp_path, "content/kb.aspose.org/en/slides/net/faq.md", (
        "Run `dotnet add package Aspose.Slides.Foss --version 1.0.0` to install.\n"
    ))
    res = sut.migrate_file(fp, "slides", "net", dry_run=False, registry=_NUGET_REGISTRY)
    assert res["result"] == sut.R_NOOP
    assert res["inline_mentions_found"] == 1


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


class TestNugetAlternateForms:
    """TC-PKG-02-08-FIX (mission MT066-2026-09-09-PACKAGE-INSTALL-RECONCILIATION):
    package_install_literal.py (ST-054 TC-02) already flags `Install-Package X`
    (PowerShell/NuGet Package Manager Console form) and
    `<PackageReference Include="X" ... />` (raw csproj XML form) as findings,
    but until this fix the migrator had no matching pattern for either --
    confirmed live against email/net: 111 real findings across 37 locales, all
    in one of these two forms, 0 files ever migrated."""

    def test_install_package_powershell_sole_command_is_migrated(self, tmp_path):
        """Matches the real, live shape (content/docs.aspose.org/en/email/net/
        getting-started/installation.md:83, confirmed against real content
        before writing this test)."""
        fp = _write(tmp_path, "content/docs.aspose.org/en/slides/net/getting-started/installation.md", (
            "### Install via Package Manager Console (Visual Studio)\n\n"
            "```powershell\n"
            "Install-Package Aspose.Slides.Foss\n"
            "```\n"
        ))
        res = sut.migrate_file(fp, "slides", "net", dry_run=False, registry=_NUGET_REGISTRY)
        assert res["result"] == sut.R_MIGRATED
        assert res["block_replacements"] == 1
        text = fp.read_text(encoding="utf-8")
        assert '{{< package-install "slides" "net" >}}' in text
        assert "Install-Package" not in text

    def test_install_package_multi_line_block_not_migrated(self, tmp_path):
        """Same structural safety bar as the dotnet-add-package path: a block
        with Install-Package PLUS other content is not a sole-command block."""
        fp = _write(tmp_path, "content/docs.aspose.org/en/slides/net/getting-started/installation.md", (
            "```powershell\n"
            "cd MyProject\n"
            "Install-Package Aspose.Slides.Foss\n"
            "```\n"
        ))
        res = sut.migrate_file(fp, "slides", "net", dry_run=False, registry=_NUGET_REGISTRY)
        assert res["result"] == sut.R_NOOP
        assert res["block_replacements"] == 0
        text = fp.read_text(encoding="utf-8")
        assert "Install-Package" in text  # untouched

    def test_install_package_inline_mention_counted_not_migrated(self, tmp_path):
        fp = _write(tmp_path, "content/kb.aspose.org/en/slides/net/faq.md", (
            "Or run `Install-Package Aspose.Slides.Foss` from the Package Manager Console.\n"
        ))
        res = sut.migrate_file(fp, "slides", "net", dry_run=False, registry=_NUGET_REGISTRY)
        assert res["result"] == sut.R_NOOP
        assert res["block_replacements"] == 0
        assert res["inline_mentions_found"] == 1

    def test_package_reference_self_closing_no_version_is_migrated(self, tmp_path):
        fp = _write(tmp_path, "content/docs.aspose.org/en/slides/net/getting-started/installation.md", (
            "```xml\n"
            '<PackageReference Include="Aspose.Slides.Foss" />\n'
            "```\n"
        ))
        res = sut.migrate_file(fp, "slides", "net", dry_run=False, registry=_NUGET_REGISTRY)
        assert res["result"] == sut.R_MIGRATED
        assert res["block_replacements"] == 1
        text = fp.read_text(encoding="utf-8")
        assert '{{< package-install "slides" "net" >}}' in text
        assert "PackageReference" not in text

    def test_package_reference_self_closing_with_version_is_migrated(self, tmp_path):
        """Matches the real, live shape (content/docs.aspose.org/en/email/net/
        getting-started/installation.md:89, confirmed against real content
        before writing this test): `<PackageReference Include="X" Version="*" />`."""
        fp = _write(tmp_path, "content/docs.aspose.org/en/slides/net/getting-started/installation.md", (
            "### Install via PackageReference (csproj)\n\n"
            "```xml\n"
            '<PackageReference Include="Aspose.Slides.Foss" Version="*" />\n'
            "```\n"
        ))
        res = sut.migrate_file(fp, "slides", "net", dry_run=False, registry=_NUGET_REGISTRY)
        assert res["result"] == sut.R_MIGRATED
        assert res["block_replacements"] == 1
        text = fp.read_text(encoding="utf-8")
        assert '{{< package-install "slides" "net" >}}' in text
        assert "<PackageReference" not in text  # the heading's own prose mention is fine

    def test_package_reference_with_body_is_migrated(self, tmp_path):
        """Body-form PackageReference (opening tag + child content + closing
        tag) spanning multiple lines, as the sole content of the fenced
        block, must migrate the same as the self-closing form."""
        fp = _write(tmp_path, "content/docs.aspose.org/en/slides/net/getting-started/installation.md", (
            "```xml\n"
            '<PackageReference Include="Aspose.Slides.Foss" Version="1.0.0">\n'
            "</PackageReference>\n"
            "```\n"
        ))
        res = sut.migrate_file(fp, "slides", "net", dry_run=False, registry=_NUGET_REGISTRY)
        assert res["result"] == sut.R_MIGRATED
        assert res["block_replacements"] == 1
        text = fp.read_text(encoding="utf-8")
        assert '{{< package-install "slides" "net" >}}' in text
        assert "PackageReference" not in text

    def test_package_reference_inside_larger_project_listing_not_migrated(self, tmp_path):
        """Negative control: a legitimate multi-line PackageReference inside a
        larger project-file listing with unrelated content (an ItemGroup
        wrapper, a second unrelated package) must NOT be treated as a sole-
        command match -- same safety bar as
        test_multi_line_block_not_migrated_as_sole_command for the CLI path."""
        fp = _write(tmp_path, "content/docs.aspose.org/en/slides/net/getting-started/installation.md", (
            "```xml\n"
            "<ItemGroup>\n"
            '  <PackageReference Include="Aspose.Slides.Foss" Version="*" />\n'
            '  <PackageReference Include="Newtonsoft.Json" Version="13.0.1" />\n'
            "</ItemGroup>\n"
            "```\n"
        ))
        res = sut.migrate_file(fp, "slides", "net", dry_run=False, registry=_NUGET_REGISTRY)
        assert res["result"] == sut.R_NOOP
        assert res["block_replacements"] == 0
        text = fp.read_text(encoding="utf-8")
        assert "Newtonsoft.Json" in text  # untouched
        assert "Aspose.Slides.Foss" in text  # untouched

    def test_package_reference_inline_mention_counted_not_migrated(self, tmp_path):
        """A <PackageReference> mention outside a fenced block (e.g. inline in
        prose) is reported via inline_mentions_found, never rewritten -- same
        treatment as an inline CLI-command mention."""
        fp = _write(tmp_path, "content/kb.aspose.org/en/slides/net/faq.md", (
            'Add `<PackageReference Include="Aspose.Slides.Foss" Version="*" />` to your .csproj.\n'
        ))
        res = sut.migrate_file(fp, "slides", "net", dry_run=False, registry=_NUGET_REGISTRY)
        assert res["result"] == sut.R_NOOP
        assert res["block_replacements"] == 0
        assert res["inline_mentions_found"] == 1
        text = fp.read_text(encoding="utf-8")
        assert "PackageReference" in text  # untouched

    def test_pypi_registry_type_unaffected_by_nuget_alt_forms(self, tmp_path):
        """Regression pin: a pypi product must never gain Install-Package or
        PackageReference sensitivity -- those are nuget-only additions."""
        fp = _write(tmp_path, "content/docs.aspose.org/en/cells/python/getting-started/installation.md", (
            "```xml\n"
            '<PackageReference Include="aspose-cells-foss" Version="*" />\n'
            "```\n"
        ))
        res = sut.migrate_file(fp, "cells", "python", dry_run=False, registry=_PYPI_REGISTRY)
        assert res["result"] == sut.R_NOOP
        assert res["block_replacements"] == 0
        assert res["inline_mentions_found"] == 0


class TestInstallPackageSingleDashVersion:
    """TC-PKG-02-01 (3d/net, mission MT066-2026-09-09-PACKAGE-INSTALL-RECONCILIATION):
    PowerShell's `Install-Package X -Version Y` uses a SINGLE-dash, case-
    insensitive parameter (`-Version`), unlike dotnet CLI's `--version`. The
    migrator only ever tolerated the double-dash spelling, so 35 real locale
    copies of 3d/net's getting-started/installation.md -- each a fenced block
    whose entire body is `Install-Package Aspose.3D -Version 26.1.0` -- were
    flagged by package_install_literal.py but never migrated. Scoped to the
    Install-Package prefix only: the other prefixes' tools do not accept a
    single-dash `-Version`, so they must NOT gain it."""

    @pytest.mark.parametrize("flag", ["-Version", "-version"])
    def test_install_package_single_dash_version_sole_block_is_migrated(self, tmp_path, flag):
        """Matches the real, live shape (content/docs.aspose.org/ar/3d/net/
        getting-started/installation.md:72, confirmed against real content)."""
        fp = _write(tmp_path, "content/docs.aspose.org/ar/slides/net/getting-started/installation.md", (
            "```powershell\n"
            f"Install-Package Aspose.Slides.Foss {flag} 26.1.0\n"
            "```\n"
        ))
        res = sut.migrate_file(fp, "slides", "net", dry_run=False, registry=_NUGET_REGISTRY)
        assert res["result"] == sut.R_MIGRATED
        assert res["block_replacements"] == 1
        text = fp.read_text(encoding="utf-8")
        assert '{{< package-install "slides" "net" >}}' in text
        assert "Install-Package" not in text
        assert "26.1.0" not in text

    def test_install_package_double_dash_version_still_migrated(self, tmp_path):
        """Regression pin: the pre-existing --version tolerance is unchanged
        for the Install-Package prefix too."""
        fp = _write(tmp_path, "content/docs.aspose.org/en/slides/net/getting-started/installation.md", (
            "```powershell\n"
            "Install-Package Aspose.Slides.Foss --version 26.1.0\n"
            "```\n"
        ))
        res = sut.migrate_file(fp, "slides", "net", dry_run=False, registry=_NUGET_REGISTRY)
        assert res["result"] == sut.R_MIGRATED
        assert res["block_replacements"] == 1

    def test_install_package_single_dash_version_with_extra_flag_not_migrated(self, tmp_path):
        """Negative control: the tolerance is one trailing version flag, not a
        blanket 'anything after the package name' loosening -- an additional
        `-Source ...` parameter makes it a multi-part command."""
        fp = _write(tmp_path, "content/docs.aspose.org/en/slides/net/getting-started/installation.md", (
            "```powershell\n"
            "Install-Package Aspose.Slides.Foss -Version 26.1.0 -Source nuget.org\n"
            "```\n"
        ))
        res = sut.migrate_file(fp, "slides", "net", dry_run=False, registry=_NUGET_REGISTRY)
        assert res["result"] == sut.R_NOOP
        assert res["block_replacements"] == 0
        assert "-Source nuget.org" in fp.read_text(encoding="utf-8")  # untouched

    def test_install_package_single_dash_version_missing_value_not_migrated(self, tmp_path):
        """Negative control: a dangling `-Version` with no value is not a
        complete, well-formed pin -- must not fullmatch."""
        fp = _write(tmp_path, "content/docs.aspose.org/en/slides/net/getting-started/installation.md", (
            "```powershell\n"
            "Install-Package Aspose.Slides.Foss -Version\n"
            "```\n"
        ))
        res = sut.migrate_file(fp, "slides", "net", dry_run=False, registry=_NUGET_REGISTRY)
        assert res["result"] == sut.R_NOOP
        assert res["block_replacements"] == 0

    def test_install_package_single_dash_version_multi_line_block_not_migrated(self, tmp_path):
        """Negative control: same multi-step-snippet safety bar as the other
        sole-command paths -- a second command in the block disqualifies it."""
        fp = _write(tmp_path, "content/docs.aspose.org/en/slides/net/getting-started/installation.md", (
            "```powershell\n"
            "cd MyProject\n"
            "Install-Package Aspose.Slides.Foss -Version 26.1.0\n"
            "```\n"
        ))
        res = sut.migrate_file(fp, "slides", "net", dry_run=False, registry=_NUGET_REGISTRY)
        assert res["result"] == sut.R_NOOP
        assert res["block_replacements"] == 0
        assert "cd MyProject" in fp.read_text(encoding="utf-8")  # untouched

    def test_dotnet_add_package_single_dash_version_not_migrated(self, tmp_path):
        """Negative control (narrow scope): `dotnet add package` does not
        accept a single-dash `-Version`, so the PowerShell spelling must NOT
        leak onto the dotnet CLI prefix."""
        fp = _write(tmp_path, "content/docs.aspose.org/en/slides/net/getting-started/installation.md", (
            "```bash\n"
            "dotnet add package Aspose.Slides.Foss -Version 26.1.0\n"
            "```\n"
        ))
        res = sut.migrate_file(fp, "slides", "net", dry_run=False, registry=_NUGET_REGISTRY)
        assert res["result"] == sut.R_NOOP
        assert res["block_replacements"] == 0
        assert "dotnet add package" in fp.read_text(encoding="utf-8")  # untouched

    def test_pypi_single_dash_version_not_migrated(self, tmp_path):
        """Negative control (narrow scope): the single-dash spelling is
        Install-Package-only -- pip must never gain it."""
        fp = _write(tmp_path, "content/docs.aspose.org/en/cells/python/getting-started/installation.md", (
            "```bash\n"
            "pip install aspose-cells-foss -Version 26.3.2\n"
            "```\n"
        ))
        res = sut.migrate_file(fp, "cells", "python", dry_run=False, registry=_PYPI_REGISTRY)
        assert res["result"] == sut.R_NOOP
        assert res["block_replacements"] == 0


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


class TestCollisionGate:
    """PKGINSTALL-COLLISION-CLASSIFIER: run_migration() must refuse to touch a
    genuinely COLLISION_RISK_STRUCTURAL product without --force. Uses the real
    cells/net registry entry -- confirmed structural collision against the
    real, committed runs/.clone_cache/aspose_cells_net -- not a synthetic
    fixture, so this proves the real wiring, not just a mocked classifier."""

    _CELLS_NET_REGISTRY = {
        "cells": {"net": {"registry_type": "nuget", "candidate": {"name": "Aspose.Cells.FOSS"}}},
    }

    def test_collision_risk_product_blocks_by_default(self, tmp_path):
        _write(tmp_path, "content/docs.aspose.org/en/cells/net/getting-started/installation.md", (
            "```bash\ndotnet add package Aspose.Cells.FOSS\n```\n"
        ))
        summary = sut.run_migration("cells", "net", dry_run=True, registry=self._CELLS_NET_REGISTRY)
        assert summary["collision_gate_blocked"] is True
        assert summary["collision_classification"] == "COLLISION_RISK_STRUCTURAL"
        assert summary["files_checked"] == 0
        assert summary["block_replacements"] == 0

    def test_force_bypasses_the_gate(self, tmp_path):
        _write(tmp_path, "content/docs.aspose.org/en/cells/net/getting-started/installation.md", (
            "```bash\ndotnet add package Aspose.Cells.FOSS\n```\n"
        ))
        summary = sut.run_migration(
            "cells", "net", dry_run=True, registry=self._CELLS_NET_REGISTRY, force=True,
        )
        assert summary["collision_gate_blocked"] is False
        assert summary["files_checked"] == 1
        assert summary["block_replacements"] == 1

    def test_respect_collision_gate_false_bypasses_too(self, tmp_path):
        _write(tmp_path, "content/docs.aspose.org/en/cells/net/getting-started/installation.md", (
            "```bash\ndotnet add package Aspose.Cells.FOSS\n```\n"
        ))
        summary = sut.run_migration(
            "cells", "net", dry_run=True, registry=self._CELLS_NET_REGISTRY,
            respect_collision_gate=False,
        )
        assert summary["collision_gate_blocked"] is False
        assert summary["files_checked"] == 1

    def test_safe_product_is_never_blocked(self, tmp_path):
        """slides/net is real-classified SAFE_FOR_MECHANICAL_MIGRATION -- the
        gate must be transparent for the overwhelming majority case."""
        _write(tmp_path, "content/docs.aspose.org/en/slides/net/getting-started/installation.md", (
            "```bash\ndotnet add package Aspose.Slides.Foss\n```\n"
        ))
        summary = sut.run_migration("slides", "net", dry_run=True, registry=_NUGET_REGISTRY)
        assert summary["collision_gate_blocked"] is False
        assert summary["collision_classification"] == "SAFE_FOR_MECHANICAL_MIGRATION"


class TestChangeBudgetGate:
    """PKGINSTALL-CHANGE-BUDGET: run_migration() must refuse a run whose
    real, probed proposed volume (files that would actually be migrated,
    not the raw candidate count) exceeds the static cap, and must record
    the ACTUAL applied count after a real execute run.

    Uses install_change_budget.configure(config_path=...) -- a real DI seam
    -- to point at a fixture budgets file, never monkeypatch.setattr on an
    internal function (this repo's own T1/T2-banned monkeypatch-lint
    policy)."""

    def _zero_budget_config(self, tmp_path) -> Path:
        cfg = tmp_path / "zero_budgets.yaml"
        cfg.write_text(
            "max_files_per_run: 0\n"
            "max_files_per_locale_per_run: 0\n"
            "anomaly_multiplier: 3.0\n"
            "warmup_runs: 3\n",
            encoding="utf-8",
        )
        return cfg

    def test_probe_pass_never_writes_before_budget_check(self, tmp_path):
        """Even in --execute mode, the probe pass must be dry-run -- content
        must be unchanged until the budget check has already passed."""
        import lib.install_change_budget as icb
        icb.configure(repo_root=tmp_path, config_path=self._zero_budget_config(tmp_path))
        path = _write(tmp_path, "content/docs.aspose.org/en/slides/net/getting-started/installation.md", (
            "```bash\ndotnet add package Aspose.Slides.Foss\n```\n"
        ))
        summary = sut.run_migration("slides", "net", dry_run=False, registry=_NUGET_REGISTRY)
        assert summary["budget_blocked"] is True
        assert "dotnet add package" in path.read_text(encoding="utf-8")  # unchanged
        icb.configure()

    def test_real_execute_records_actual_applied_count(self, tmp_path):
        import lib.install_change_budget as icb
        icb.configure(repo_root=tmp_path)
        _write(tmp_path, "content/docs.aspose.org/en/slides/net/getting-started/installation.md", (
            "```bash\ndotnet add package Aspose.Slides.Foss\n```\n"
        ))
        summary = sut.run_migration("slides", "net", dry_run=False, registry=_NUGET_REGISTRY)
        assert summary["budget_blocked"] is False
        assert summary["files_migrated"] == 1
        history = icb.load_history()
        assert history["slides/mechanical_migration"] == [1]
        icb.configure()

    def test_force_bypasses_the_budget_gate_too(self, tmp_path):
        import lib.install_change_budget as icb
        icb.configure(repo_root=tmp_path, config_path=self._zero_budget_config(tmp_path))
        _write(tmp_path, "content/docs.aspose.org/en/slides/net/getting-started/installation.md", (
            "```bash\ndotnet add package Aspose.Slides.Foss\n```\n"
        ))
        summary = sut.run_migration("slides", "net", dry_run=False, registry=_NUGET_REGISTRY, force=True)
        assert summary["budget_blocked"] is False
        assert summary["files_migrated"] == 1
        icb.configure()

    def test_respect_change_budget_false_bypasses_too(self, tmp_path):
        import lib.install_change_budget as icb
        icb.configure(repo_root=tmp_path, config_path=self._zero_budget_config(tmp_path))
        _write(tmp_path, "content/docs.aspose.org/en/slides/net/getting-started/installation.md", (
            "```bash\ndotnet add package Aspose.Slides.Foss\n```\n"
        ))
        summary = sut.run_migration(
            "slides", "net", dry_run=False, registry=_NUGET_REGISTRY, respect_change_budget=False,
        )
        assert summary["budget_blocked"] is False
        assert summary["files_migrated"] == 1
        icb.configure()
