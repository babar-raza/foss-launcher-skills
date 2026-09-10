"""
Tests for scripts/pipeline/audit/package_install_literal.py (Mission
MT015-2026-07-30-PACKAGE-REGISTRY, TC-MT015-05).
"""

import sys
from pathlib import Path

_PIPELINE_ROOT = Path(__file__).resolve().parents[1]
if str(_PIPELINE_ROOT) not in sys.path:
    sys.path.insert(0, str(_PIPELINE_ROOT))

from audit.package_install_literal import (  # noqa: E402
    verify_package_install_literals, _is_noise_match, _INSTALL_CMD_RE, _strip_shortcode_calls,
)


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
        line for an unregistered pair is now a FAIL.

        PKGINSTALL-REGEX-NARROWING (2026-09-10): the fixture package name
        must plausibly be about Aspose (contain "aspose") -- a token with no
        connection to any Aspose package is exactly the noise category this
        gate now drops (see TestVerifyPackageInstallLiteralsNarrowing for
        that case covered explicitly)."""
        page = _write(tmp_path, "pip install aspose-some-unregistered-family\n")
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
        """End-to-end proof against the actual shipped ar/note/python/_index.md.

        Originally pinned at 2 findings on line 38 (both occurrences still
        literal). Commit 65c59fbaba (ST-054 mechanical migration, landed
        after this test was first written) migrated the line's second
        occurrence to a {{< package-install-inline ... >}} call, leaving
        exactly 1 literal occurrence on that line today -- real content
        drift, not a regression in the multi-match fix this test guards.
        Floor of >=1 (not an exact count) so the test survives further
        unrelated edits to the file."""
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
        assert len(line_38) >= 1, (
            f"expected >=1 finding on line 38 of the real file, got {len(line_38)}: {line_38}"
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


class TestIsNoiseMatchUnit:
    """PKGINSTALL-REGEX-NARROWING (2026-09-10) unit-level tests, exercising
    `_is_noise_match` directly against real `_INSTALL_CMD_RE` match objects --
    every dropped shape below was found live in the real portfolio during
    this taskcard's validation pass (validate_narrowing.py sweep against the
    full corpus), not invented."""

    def _match(self, text: str):
        m = _INSTALL_CMD_RE.search(text)
        assert m is not None, f"fixture text did not match _INSTALL_CMD_RE at all: {text!r}"
        return m

    def test_flag_shaped_tokens_are_noise(self):
        for text in [
            "pip install --upgrade",
            "pip install -e",
            "npm install -D",
            "pip install -r",
        ]:
            assert _is_noise_match(self._match(text)) is True, text

    def test_unrelated_real_package_is_noise(self):
        for text in ["pip install fastmcp", "pip install pywin32"]:
            assert _is_noise_match(self._match(text)) is True, text

    def test_markdown_table_pipe_artifact_is_noise(self):
        assert _is_noise_match(self._match("pip install |")) is True

    def test_locale_translation_fragment_is_noise(self):
        """Real, live machine-translation defects: 'install X and Y' /
        '...using the pip install command' sentences mistranslated, leaving
        the English verb phrase attached to a foreign word for 'and'/
        'command'. Confirmed across ~67 real files (see validate_narrowing.py
        output) -- these are a genuine, separate defect class (filed to
        backlog), but not an instance of THIS gate's install-command
        defect, so they must be dropped here."""
        for text in [
            "pip install dan",
            "pip install och",
            "pip install komanda.",
            "go get használatával,",
        ]:
            assert _is_noise_match(self._match(text)) is True, text

    def test_wrong_but_plausibly_aspose_name_is_not_noise(self):
        """Deliberately loose, not exact-candidate matching: a WRONG name
        that still contains 'aspose' must keep being flagged -- that's this
        gate's actual job (3D-NET-REFRESH-002's defect class)."""
        for text in [
            "dotnet add package Aspose.Cells_FOSS",
            "dotnet add package Aspose.3D.Converter",
        ]:
            assert _is_noise_match(self._match(text)) is False, text

    def test_known_uncaught_edge_case_documented_not_silently_fixed(self):
        """A real, different, legitimately-documented package that happens
        to contain 'aspose' in its own name (36 real occurrences) is a known,
        explicitly-accepted residual limitation of the 'contains aspose'
        rule -- exact-candidate-matching would close it but reopen the
        3D-NET-REFRESH-002 false-negative risk this gate exists to prevent.
        This test pins the documented tradeoff, not a bug."""
        assert _is_noise_match(self._match("pip install markitdown-aspose-cells-plugin")) is False

    def test_package_reference_xml_is_never_filtered(self):
        """match.group(2) is None for the <PackageReference> alternative --
        a full-portfolio sweep found zero noise in that shape, so it must
        never be treated as noise regardless of its Include value."""
        m = _INSTALL_CMD_RE.search('<PackageReference Include="SomeUnrelatedThing" />')
        assert m is not None
        assert m.group(2) is None
        assert _is_noise_match(m) is False


class TestVerifyPackageInstallLiteralsNarrowing:
    """PKGINSTALL-REGEX-NARROWING (2026-09-10) integration-level tests,
    proving the narrowing is wired into both finditer loops of
    verify_package_install_literals (unregistered-entry branch and the
    registered published/unpublished branches)."""

    def test_flag_and_unrelated_package_noise_dropped_for_published_entry(self, tmp_path):
        page = _write(
            tmp_path,
            "pip install --upgrade\n"
            "pip install -r\n"
            "pip install fastmcp\n"
            "pip install aspose-words-foss\n",
        )
        findings = verify_package_install_literals(page, "words", "net", registry=_registry("pypi", True))
        assert len(findings) == 1
        assert "aspose-words-foss" in findings[0].message

    def test_translation_artifact_noise_dropped_for_unregistered_entry(self, tmp_path):
        """TC-MT018-07's unregistered-entry branch must apply the same
        narrowing -- a translation artifact for a family with no registry
        entry at all must not be a spurious UNREGISTERED finding."""
        page = _write(tmp_path, "pip install dan konfiguracja.\n")
        findings = verify_package_install_literals(page, "unknown-family", "python", registry={})
        assert findings == []

    def test_cells_net_real_collision_still_flagged(self, tmp_path):
        """Real, live defect this gate must keep catching: the C# namespace
        Aspose.Cells_FOSS used where the real NuGet package ID is
        Aspose.Cells.FOSS."""
        page = _write(tmp_path, "dotnet add package Aspose.Cells_FOSS\n")
        findings = verify_package_install_literals(page, "cells", "net", registry=_registry("nuget", True))
        assert len(findings) == 1

    def test_3d_net_refresh_002_shaped_wrong_name_still_flagged_when_unpublished(self, tmp_path):
        registry_3d_net = {
            "3d": {"net": {
                "registry_type": "nuget",
                "candidate": {"name": "Aspose.3D.FOSS"},
                "candidate_owner": "asposefoss",
                "verification": {"published": False, "verified_at": None, "verified_owner": None,
                                  "evidence_url": None, "method": None},
                "owner_match": None,
            }}
        }
        page = _write(tmp_path, "dotnet add package Aspose.3D.Converter\n")
        findings = verify_package_install_literals(page, "3d", "net", registry=registry_3d_net)
        assert len(findings) == 1
        assert "UNPUBLISHED" in findings[0].message

    def test_markdown_table_pipe_artifact_dropped(self, tmp_path):
        page = _write(
            tmp_path,
            "| Method | Command |\n"
            "|---|---|\n"
            "| pip | pip install |\n",
        )
        findings = verify_package_install_literals(page, "words", "net", registry=_registry("pypi", True))
        assert findings == []

    def test_known_edge_case_package_still_flagged_end_to_end(self, tmp_path):
        """Documented residual limitation (see TestIsNoiseMatchUnit) holds
        end-to-end too, not just at the match-level."""
        page = _write(tmp_path, "pip install markitdown-aspose-cells-plugin\n")
        findings = verify_package_install_literals(page, "words", "net", registry=_registry("pypi", True))
        assert len(findings) == 1

    def test_before_after_delta_on_a_mixed_fixture(self, tmp_path):
        """A single fixture combining every discovered noise category plus
        two genuine findings -- documents the exact shape of the narrowing's
        effect (5 lines of noise dropped, 2 real findings kept), the kind of
        before/after delta this taskcard's acceptance checks require being
        spot-checked and published, not silently absorbed."""
        page = _write(
            tmp_path,
            "pip install --upgrade\n"
            "pip install -e\n"
            "pip install fastmcp\n"
            "pip install |\n"
            "pip install och\n"
            "pip install aspose-words-foss\n"
            'pip install "aspose-words-foss[extras]"\n',
        )
        findings = verify_package_install_literals(page, "words", "net", registry=_registry("pypi", True))
        assert len(findings) == 2
        assert all("aspose-words-foss" in f.message for f in findings)


class TestShortcodeCallSpanStripping:
    """PKGINSTALL-REGEX-NARROWING (2026-09-10): incidental real bug found
    while writing this taskcard's regression tests, not the narrowing itself
    -- `_is_noise_line`'s old blanket 'skip the whole line if it contains the
    shortcode marker' check silently hid a co-located leftover literal
    install command on the same physical line as a real shortcode call. Real,
    live shape (not hypothetical): content/docs.aspose.org/ar/note/python/
    _index.md:38, post commit 65c59fbaba (ST-054 mechanical migration),
    carries both `{{< package-install-inline "note" "python" >}}` AND a
    still-literal `pip install aspose-note` on the same line -- the old code
    produced 0 findings for that line; must now produce 1. Fixed by
    stripping only the shortcode call's own span (which never itself matches
    _INSTALL_CMD_RE) instead of skipping the entire line."""

    def test_strip_removes_only_the_call_span(self):
        assert (
            _strip_shortcode_calls('Install:\n\n{{< package-install "words" "net" >}}\n')
            == "Install:\n\n\n"
        )
        assert _strip_shortcode_calls('{{< package-install-inline "note" "python" >}}') == ""

    def test_strip_leaves_unrelated_text_untouched(self):
        assert _strip_shortcode_calls("dotnet add package Aspose.Words.FOSS") == (
            "dotnet add package Aspose.Words.FOSS"
        )

    def test_leftover_literal_on_the_same_line_as_a_shortcode_call_is_still_flagged(self, tmp_path):
        page = _write(
            tmp_path,
            '`pip install aspose-note`.PDF requires `reportlab` '
            '({{< package-install-inline "note" "python" >}}).\n',
        )
        registry = {
            "note": {"python": {
                "registry_type": "pypi",
                "candidate": {"name": "aspose-note"},
                "candidate_owner": "aspose-note",
                "verification": {"published": True, "verified_at": None,
                                  "verified_owner": None, "evidence_url": None, "method": None},
                "owner_match": None,
            }}
        }
        findings = verify_package_install_literals(page, "note", "python", registry=registry)
        assert len(findings) == 1
        assert "aspose-note" in findings[0].message

    def test_bare_shortcode_call_with_no_other_literal_still_produces_no_findings(self, tmp_path):
        page = _write(tmp_path, 'Install:\n\n{{< package-install "words" "net" >}}\n')
        findings = verify_package_install_literals(page, "words", "net", registry=_registry("nuget", True))
        assert findings == []
