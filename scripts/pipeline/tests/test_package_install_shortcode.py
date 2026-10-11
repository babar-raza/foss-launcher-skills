"""
Tests for layouts/shortcodes/package-install.html and its 3 siblings
(package-install-inline.html, maven-coord.html, maven-gav.html), plus the
shared layouts/partials/shortcodes/foss-source-install.html partial (Mission
MT015-2026-07-30-PACKAGE-REGISTRY TC-MT015-05; ST-054 TC-13, GitHub-fallback
rendering fix, governing plan §Q).

Hugo template logic can't be unit-tested in Python directly (no existing
precedent in this repo for shelling out to a live hugo binary from pytest --
same gap already documented in test_foss_packages_data.py's own docstring for
maven-coord/maven-gav). This file pins the source text against regression
instead, and records what WAS independently verified this session via real
`hugo build` runs (hugo v0.140.1, D:/hugo/hugo_0.140.1/hugo.exe) against
isolated, non-committed fixture sites:

Pre-TC-13 (published branches, and the OLD unpublished notice -- superseded):
  - pypi published:      `pip install aspose-scratchtest-foss`
  - npm published:       `npm install @asposefoss/scratchtest`
  - go_modules published:`go get github.com/aspose-scratchtest-foss/aspose-scratchtest-foss-for-go`
  - nuget unpublished (real words/net data, since retracted): the old
    "not yet published" notice (ST-054 TC-13 replaced this)
  - missing entry:       build fails, exit 1
  - registry_type="maven" misuse: build fails with the documented redirect
    message pointing at maven-coord/maven-gav/cargo-crate instead

TC-13 (2026-09-10): real fixture builds against the actual, current
data/products.json confirmed the unpublished branch of all 4 shortcodes now
renders a real git-clone-based command per ecosystem (python/typescript/net/
cpp/go/java), using the real cmake_target for slides/cpp, pdf/cpp, email/cpp
(TC-12's enrichment), with zero "not yet published"/"coming soon" text
anywhere in rendered output. See scripts/pipeline/tests/test_input_manifest.py
and test_enrich_products_cmake_targets.py for the underlying extraction's own
test coverage.
"""

from pathlib import Path

_LAYOUTS_ROOT = Path(__file__).resolve().parents[3] / "layouts"
_SHORTCODE_PATH = _LAYOUTS_ROOT / "shortcodes" / "package-install.html"
_INLINE_SHORTCODE_PATH = _LAYOUTS_ROOT / "shortcodes" / "package-install-inline.html"
_MAVEN_COORD_PATH = _LAYOUTS_ROOT / "shortcodes" / "maven-coord.html"
_MAVEN_GAV_PATH = _LAYOUTS_ROOT / "shortcodes" / "maven-gav.html"
_PARTIAL_PATH = _LAYOUTS_ROOT / "partials" / "shortcodes" / "foss-source-install.html"


def _source() -> str:
    return _SHORTCODE_PATH.read_text(encoding="utf-8")


def _template_logic_only(src: str) -> str:
    """Strip the leading `{{- /* ... */ -}}` doc comment, so a check for
    "does the ACTIVE TEMPLATE still contain phrase X" isn't confused by
    prose in a comment that legitimately *references* the old, now-fixed
    behavior for context (e.g. "no longer renders 'not yet published'")."""
    marker = "*/ -}}"
    idx = src.find(marker)
    return src[idx + len(marker):] if idx != -1 else src


def test_shortcode_file_exists():
    assert _SHORTCODE_PATH.is_file()


def test_reads_from_unified_package_registry_data():
    src = _source()
    assert "site.Data.package_registry" in src
    # Must never read the retired, now-deleted split files.
    assert "foss_packages" not in src
    assert "cargo_packages" not in src


def test_errorfs_on_missing_entry():
    assert "errorf" in _source()


def test_redirects_maven_and_cargo_to_their_dedicated_shortcodes():
    """Regression pin: this shortcode must refuse to render maven/cargo entries
    rather than silently duplicating maven-coord/maven-gav/cargo-crate's
    already-proven, byte-parity-verified rendering logic."""
    src = _source()
    assert 'eq $entry.registry_type "maven"' in src
    assert 'eq $entry.registry_type "cargo"' in src
    assert "maven-coord/maven-gav/cargo-crate" in src


def test_handles_all_four_covered_registry_types():
    src = _source()
    for registry_type in ("pypi", "nuget", "npm", "go_modules"):
        assert f'eq $entry.registry_type "{registry_type}"' in src, (
            f"missing branch for registry_type={registry_type!r}"
        )


def test_never_fabricates_a_live_registry_command_when_unpublished():
    """The unpublished branch must never guess a specific live-registry command
    for an unconfirmed package (root cause 1 from the governing plan) -- but,
    per ST-054 TC-13, it also must never render a bare "not yet published"
    disclosure with no actionable next step (explicit operator policy,
    2026-09-03/2026-09-10: publication status is internal-only, a public page
    must always show a real, working command). It must instead delegate to
    the shared foss-source-install partial."""
    src = _source()
    assert "not yet published" not in _template_logic_only(src)
    assert 'partial "shortcodes/foss-source-install.html"' in src
    # The unpublished branch must come before any registry-specific command
    # branch in source order, so it's reached first for verification.published=false.
    unpublished_idx = src.index('partial "shortcodes/foss-source-install.html"')
    pypi_idx = src.index('eq $entry.registry_type "pypi"')
    assert unpublished_idx < pypi_idx


def test_inline_shortcode_never_says_not_yet_published():
    src = _INLINE_SHORTCODE_PATH.read_text(encoding="utf-8")
    assert "not yet published" not in _template_logic_only(src)
    assert 'partial "shortcodes/foss-source-install.html"' in src
    assert '"mode" "inline"' in src


def test_maven_coord_never_says_not_yet_published():
    src = _MAVEN_COORD_PATH.read_text(encoding="utf-8")
    assert "not yet published" not in _template_logic_only(src)
    assert 'partial "shortcodes/foss-source-install.html"' in src
    assert '"mode" "block"' in src


def test_maven_gav_never_says_not_yet_published():
    src = _MAVEN_GAV_PATH.read_text(encoding="utf-8")
    assert "not yet published" not in _template_logic_only(src)
    assert 'partial "shortcodes/foss-source-install.html"' in src
    assert '"mode" "inline"' in src


def test_cargo_crate_is_not_modified_by_this_fix():
    """cargo-crate.html is the one already-correct shortcode -- the reference
    pattern the others are brought up to match, not a file this fix touches.
    It must keep its own evidence_url-based fallback, never delegate to the
    new shared partial."""
    src = (_LAYOUTS_ROOT / "shortcodes" / "cargo-crate.html").read_text(encoding="utf-8")
    assert "verification.evidence_url" in src
    assert "foss-source-install" not in src


class TestFossSourceInstallPartial:
    """Pinned-source tests for the new shared partial (ST-054 TC-13)."""

    @staticmethod
    def _source() -> str:
        return _PARTIAL_PATH.read_text(encoding="utf-8")

    def test_partial_file_exists(self):
        assert _PARTIAL_PATH.is_file()

    def test_reads_from_products_json_not_evidence_url(self):
        src = self._source()
        assert "site.Data.products" in src
        # Must never generalize cargo-crate.html's own evidence_url pattern --
        # confirmed unsafe (slides/net's evidence_url is a NuGet-probe API
        # endpoint, not a source URL). See governing plan §Q.2.
        assert "verification.evidence_url" not in _template_logic_only(src)

    def test_errorfs_on_missing_products_entry(self):
        src = self._source()
        assert "errorf" in src
        assert "no data/products.json entry" in src

    def test_errorfs_on_unrecognized_platform(self):
        src = self._source()
        assert "add an ecosystem branch" in src

    def test_all_six_ecosystem_branches_present(self):
        src = self._source()
        for platform in ("python", "typescript", "net", "cpp", "go", "java"):
            assert f'eq $platform "{platform}"' in src, f"missing branch for platform={platform!r}"

    def test_inline_mode_never_branches_on_platform(self):
        """The inline variant must always be the same short git-clone snippet
        regardless of ecosystem -- no per-platform branching in that path."""
        src = self._source()
        inline_idx = src.index('eq $mode "inline"')
        python_idx = src.index('eq $platform "python"')
        assert inline_idx < python_idx

    def test_cpp_branch_uses_real_extracted_target_when_present(self):
        src = self._source()
        assert "$product.cmake_target" in src

    def test_cpp_branch_falls_back_when_no_extracted_target(self):
        """Never guesses a target name -- degrades to a generic snippet plus a
        README pointer only when cmake_target is null (governing plan §Q.3a)."""
        src = self._source()
        assert "see the repository's own README" in src

    def test_go_branch_uses_registry_module_path_not_a_guess(self):
        src = self._source()
        assert "$entry.candidate.module_path" in src

    def test_never_says_not_yet_published_or_coming_soon(self):
        src = _template_logic_only(self._source())
        assert "not yet published" not in src
        assert "coming soon" not in src
