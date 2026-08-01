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
