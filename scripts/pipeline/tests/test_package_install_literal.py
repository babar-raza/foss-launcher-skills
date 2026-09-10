"""
Tests for scripts/pipeline/audit/package_install_literal.py (Mission
MT015-2026-07-30-PACKAGE-REGISTRY, TC-MT015-05).
"""

import sys
from pathlib import Path

_PIPELINE_ROOT = Path(__file__).resolve().parents[1]
if str(_PIPELINE_ROOT) not in sys.path:
    sys.path.insert(0, str(_PIPELINE_ROOT))

from audit.package_install_literal import verify_package_install_literals  # noqa: E402


def _registry(registry_type: str, published: bool) -> dict:
    return {
        "words": {"net": {
            "registry_type": registry_type,
            "candidate": {"name": "Aspose.Words.FOSS"},
            "candidate_owner": "asposefoss",
            "verification": {"published": published, "verified_at": None, "verified_owner": None,
                              "evidence_url": None, "method": None},
            "owner_match": None,
        }}
    }


def _write(tmp_path, text):
    p = tmp_path / "page.md"
    p.write_text(text, encoding="utf-8")
    return p


class TestPublishedFamilyLiteralIsBanned:
    def test_literal_command_flagged_when_published(self, tmp_path):
        page = _write(tmp_path, "Install:\n\ndotnet add package Aspose.Words.FOSS\n")
        findings = verify_package_install_literals(page, "words", "net", registry=_registry("nuget", True))
        assert len(findings) == 1
        assert findings[0].level == "FAIL"
        assert "package-install" in findings[0].suggestion

    def test_shortcode_call_is_not_flagged(self, tmp_path):
        page = _write(tmp_path, 'Install:\n\n{{< package-install "words" "net" >}}\n')
        findings = verify_package_install_literals(page, "words", "net", registry=_registry("nuget", True))
        assert findings == []

    def test_no_command_present_no_findings(self, tmp_path):
        page = _write(tmp_path, "Some unrelated prose about Aspose.Words.FOSS as a concept.\n")
        findings = verify_package_install_literals(page, "words", "net", registry=_registry("nuget", True))
        assert findings == []


class TestUnpublishedFamilySpecificCommandIsFabrication:
    def test_specific_command_flagged_as_fabrication_when_unpublished(self, tmp_path):
        """Root cause 1 / 3D-NET-REFRESH-002's defect class: a specific command
        for an unconfirmed package is a fabrication risk, not just a staleness
        risk -- must be flagged distinctly."""
        page = _write(tmp_path, "dotnet add package Aspose.Words.FOSS\n")
        findings = verify_package_install_literals(page, "words", "net", registry=_registry("nuget", False))
        assert len(findings) == 1
        assert "UNPUBLISHED" in findings[0].message
        assert "3D-NET-REFRESH-002" in findings[0].suggestion

    def test_canonical_fallback_prose_is_not_flagged(self, tmp_path):
        page = _write(tmp_path, "A NuGet package has not been published yet, build from source.\n")
        findings = verify_package_install_literals(page, "words", "net", registry=_registry("nuget", False))
        assert findings == []


class TestScopeGuards:
    def test_maven_registry_type_not_covered_here(self, tmp_path):
        """Maven has its own dedicated gate (maven_coordinates.py) -- this
        module must not double-flag it."""
        page = _write(tmp_path, "mvn dependency:get -Dartifact=org.aspose:aspose-cells-foss:1.0\n")
        findings = verify_package_install_literals(page, "cells", "java", registry=_registry("maven", True))
        assert findings == []

    def test_cargo_registry_type_not_covered_here(self, tmp_path):
        page = _write(tmp_path, "cargo add aspose-cells-foss-rust\n")
        findings = verify_package_install_literals(page, "cells", "rust", registry=_registry("cargo", True))
        assert findings == []

    def test_no_registry_entry_with_install_command_is_now_a_fail(self, tmp_path):
        """TC-MT018-07: a family/platform with NO registry entry at all is no
        longer a silent pass -- this was the exact blind spot that let 14
        launched products ship fabricated/never-published install commands
        undetected (2026-08-01 full-repo audit). An install-command-shaped
        line for an unregistered pair is now a FAIL."""
        page = _write(tmp_path, "pip install some-unrelated-package\n")
        findings = verify_package_install_literals(page, "unknown-family", "python", registry={})
        assert len(findings) == 1
        assert "UNREGISTERED" in findings[0].message

    def test_no_registry_entry_no_install_command_still_clean(self, tmp_path):
        """The fail-on-missing-entry rule only fires when an install-command
        pattern is actually present -- a page with no install text at all for
        an unregistered pair is still clean (nothing to flag)."""
        page = _write(tmp_path, "This page has no install instructions at all.\n")
        findings = verify_package_install_literals(page, "unknown-family", "python", registry={})
        assert findings == []

    def test_missing_family_or_platform_no_findings(self, tmp_path):
        page = _write(tmp_path, "npm install @asposefoss/pdf\n")
        assert verify_package_install_literals(page, None, "typescript", registry=_registry("npm", True)) == []
        assert verify_package_install_literals(page, "pdf", None, registry=_registry("npm", True)) == []


class TestInstallPackageAndPackageReferenceDetection:
    """ST-054 TC-02: _INSTALL_CMD_RE previously missed PowerShell's
    Install-Package syntax and raw .csproj <PackageReference> XML, both real
    and live in .NET-family content (content/docs.aspose.org/en/cells/net/
    getting-started/installation.md) -- undercounting true .NET scope in
    every sweep before this fix."""

    def test_install_package_powershell_syntax_flagged_when_published(self, tmp_path):
        page = _write(tmp_path, "Run this in the Package Manager Console:\n\nInstall-Package Aspose.Words.FOSS\n")
        findings = verify_package_install_literals(page, "words", "net", registry=_registry("nuget", True))
        assert len(findings) == 1
        assert findings[0].level == "FAIL"

    def test_package_reference_xml_flagged_when_published(self, tmp_path):
        page = _write(
            tmp_path,
            'Add to your .csproj:\n\n<PackageReference Include="Aspose.Words.FOSS" Version="*" />\n',
        )
        findings = verify_package_install_literals(page, "words", "net", registry=_registry("nuget", True))
        assert len(findings) == 1
        assert findings[0].level == "FAIL"

    def test_install_package_flagged_as_fabrication_when_unpublished(self, tmp_path):
        page = _write(tmp_path, "Install-Package Aspose.Words.FOSS\n")
        findings = verify_package_install_literals(page, "words", "net", registry=_registry("nuget", False))
        assert len(findings) == 1
        assert "UNPUBLISHED" in findings[0].message

    def test_package_reference_with_different_attribute_order_still_matches(self, tmp_path):
        page = _write(tmp_path, '<PackageReference Include="Aspose.Cells_FOSS" />\n')
        findings = verify_package_install_literals(page, "words", "net", registry=_registry("nuget", True))
        assert len(findings) == 1

    def test_existing_pip_dotnet_npm_go_patterns_still_work_alongside_the_new_ones(self, tmp_path):
        """Regression guard: the regex extension must not break any of the 4
        original patterns it was OR'd onto."""
        for cmd, registry_type in [
            ("pip install aspose-words-foss", "pypi"),
            ("dotnet add package Aspose.Words.FOSS", "nuget"),
            ("npm install @asposefoss/words", "npm"),
            ("go get github.com/aspose-words-foss/x", "go_modules"),
        ]:
            page = _write(tmp_path, f"{cmd}\n")
            findings = verify_package_install_literals(page, "words", "net", registry=_registry(registry_type, True))
            assert len(findings) == 1, f"expected a finding for {cmd!r} ({registry_type})"

    def test_bare_word_packagereference_without_xml_shape_is_not_flagged(self, tmp_path):
        """No false positive: prose mentioning 'PackageReference' generically,
        not the actual XML tag shape, must not match."""
        page = _write(tmp_path, "The PackageReference element is how .NET projects declare dependencies.\n")
        findings = verify_package_install_literals(page, "words", "net", registry=_registry("nuget", True))
        assert findings == []


class TestTroubleshootingHeadingFalsePositiveGuard:
    """Regression pin for a real false positive found before this gate went
    live: content/kb.aspose.org/en/words/net/troubleshooting.md has the
    heading '### `dotnet add package Aspose.Words` cannot find the package'
    -- explaining the command DOESN'T work, not asserting it as an install
    instruction. Confirmed via the actual repo file, not a hypothetical."""

    def test_heading_explaining_command_failure_is_not_flagged(self, tmp_path):
        page = _write(
            tmp_path,
            "### `dotnet add package Aspose.Words` cannot find the package\n\n"
            "A NuGet package has not been published yet for this FOSS edition. "
            "Run `git clone`...\n",
        )
        findings = verify_package_install_literals(page, "words", "net", registry=_registry("nuget", False))
        assert findings == []

    def test_body_text_repeating_the_same_command_outside_a_heading_is_still_flagged(self, tmp_path):
        """The heading guard must not become a blanket bypass -- the same
        command as plain prose (not a heading) must still be caught."""
        page = _write(
            tmp_path,
            "### Some other heading\n\n"
            "Just run dotnet add package Aspose.Words.FOSS to install it.\n",
        )
        findings = verify_package_install_literals(page, "words", "net", registry=_registry("nuget", False))
        assert len(findings) == 1

    def test_against_the_real_troubleshooting_file(self):
        """End-to-end proof against the actual shipped file, not a synthetic
        reproduction -- must produce zero findings."""
        real_path = (
            Path(__file__).resolve().parents[3]
            / "content" / "kb.aspose.org" / "en" / "words" / "net" / "troubleshooting.md"
        )
        if not real_path.is_file():
            import pytest
            pytest.skip("real troubleshooting.md not present in this checkout")
        findings = verify_package_install_literals(
            real_path, "words", "net", registry=_registry("nuget", False)
        )
        assert findings == [], f"false positive(s) against real shipped content: {findings}"


class TestMultipleOccurrencesOnOneLine:
    """ST-054 TC-17: _INSTALL_CMD_RE.search(line) capped detection at one
    match per line in every branch (unregistered/published/unpublished),
    silently undercounting any line with more than one independent
    install-command mention -- structurally different from an ordinary
    false-negative, since fixing the first occurrence on a line simply
    promoted the second into view on some *future* sweep rather than the
    current one, which is consistent with why this campaign's own baseline
    sweeps (6,522 / 6,248 / 6,454 on 2026-09-10) never reconciled with each
    other. Both golden fixtures below are pulled verbatim from real, live
    content -- not synthetic reproductions -- confirmed by direct read
    before this fix landed."""

    def _registry_note_python(self, published: bool) -> dict:
        return {
            "note": {"python": {
                "registry_type": "pypi",
                "candidate": {"name": "aspose-note"},
                "candidate_owner": "aspose-note",
                "verification": {"published": published, "verified_at": None,
                                  "verified_owner": None, "evidence_url": None, "method": None},
                "owner_match": None,
            }}
        }

    def test_two_pip_install_mentions_on_one_line_both_flagged(self, tmp_path):
        """Golden fixture, verbatim from content/docs.aspose.org/ar/note/python/_index.md:38
        (confirmed via direct read 2026-09-10): a base-package `pip install`
        mention and a separate optional-extras `pip install "X[pdf]"` mention
        share one line, in Arabic prose with no space after the first
        closing backtick. Previously produced exactly 1 finding; must now
        produce 2."""
        page = _write(
            tmp_path,
            'مطلوب Python 3.10 أو أعلى. `pip install aspose-note`.PDF تطلب '
            '`reportlab` (مقرر مع `pip install "aspose-note[pdf]"`).\n',
        )
        findings = verify_package_install_literals(
            page, "note", "python", registry=self._registry_note_python(True)
        )
        assert len(findings) == 2, f"expected 2 findings (one per occurrence), got {findings}"
        assert all(f.line_no == 1 for f in findings)

    def test_matched_span_stops_at_closing_backtick_not_trailing_prose(self, tmp_path):
        """Same fixture: the FIRST match's reported identifier must be the
        real span (`aspose-note`), not the pre-fix overcapture that swallowed
        the closing backtick and the next word (`aspose-note`.PDF`) -- the
        capture-group boundary fix, proven on the same real line as the
        multi-match fix above."""
        page = _write(
            tmp_path,
            'مطلوب Python 3.10 أو أعلى. `pip install aspose-note`.PDF تطلب '
            '`reportlab` (مقرر مع `pip install "aspose-note[pdf]"`).\n',
        )
        findings = verify_package_install_literals(
            page, "note", "python", registry=self._registry_note_python(True)
        )
        first = findings[0]
        assert "aspose-note`.PDF" not in first.message
        assert "pip install aspose-note" in first.message

    def test_against_the_real_note_python_index_file(self):
        """End-to-end proof against the actual shipped ar/note/python/_index.md
        -- must find at least the 2 known occurrences on line 38 (real content
        may carry more elsewhere in the file; this is a floor, not an exact
        count, so the test survives unrelated future edits to the file)."""
        real_path = (
            Path(__file__).resolve().parents[3]
            / "content" / "docs.aspose.org" / "ar" / "note" / "python" / "_index.md"
        )
        if not real_path.is_file():
            import pytest
            pytest.skip("real ar/note/python/_index.md not present in this checkout")
        findings = verify_package_install_literals(
            real_path, "note", "python", registry=self._registry_note_python(True)
        )
        line_38 = [f for f in findings if f.line_no == 38]
        assert len(line_38) >= 2, (
            f"expected >=2 findings on line 38 of the real file (multi-occurrence "
            f"regression), got {len(line_38)}: {line_38}"
        )

    def test_against_the_real_products_note_python_index_file(self):
        """Second real fixture, higher density: content/products.aspose.org/
        ar/note/python/_index.md has 3 separate lines (19, 47, 96) each with
        two independent pip-install mentions (base package + [pdf] extra),
        confirmed via direct read 2026-09-10. Proves the fix holds across
        multiple lines in one file, not just the single-line case above."""
        real_path = (
            Path(__file__).resolve().parents[3]
            / "content" / "products.aspose.org" / "ar" / "note" / "python" / "_index.md"
        )
        if not real_path.is_file():
            import pytest
            pytest.skip("real products.aspose.org ar/note/python/_index.md not present")
        findings = verify_package_install_literals(
            real_path, "note", "python", registry=self._registry_note_python(True)
        )
        for expected_line in (19, 47, 96):
            on_line = [f for f in findings if f.line_no == expected_line]
            assert len(on_line) >= 2, (
                f"expected >=2 findings on line {expected_line}, got {len(on_line)}: {on_line}"
            )
