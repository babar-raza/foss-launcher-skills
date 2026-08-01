"""
Tests for layouts/shortcodes/package-install.html (Mission
MT015-2026-07-30-PACKAGE-REGISTRY, TC-MT015-05).

Hugo template logic can't be unit-tested in Python directly (no existing
precedent in this repo for shelling out to a live hugo binary from pytest --
same gap already documented in test_foss_packages_data.py's own docstring for
maven-coord/maven-gav). This file pins the source text against regression
instead, and records what WAS independently verified this session via a real
`hugo` build (v0.154.5-extended, found via winget) against a temporary,
non-committed fixture (3 registries' published branch + a real unpublished
words/net entry + both errorf paths -- all 6 confirmed correct, then the
fixture data and scratch content pages were fully reverted before commit):

  - pypi published:      `pip install aspose-scratchtest-foss`
  - npm published:       `npm install @asposefoss/scratchtest`
  - go_modules published:`go get github.com/aspose-scratchtest-foss/aspose-scratchtest-foss-for-go`
  - nuget unpublished (real words/net data): the "not yet published" notice
  - missing entry:       build fails, exit 1
  - registry_type="maven" misuse: build fails with the documented redirect
    message pointing at maven-coord/maven-gav/cargo-crate instead
"""

from pathlib import Path

_SHORTCODE_PATH = (
    Path(__file__).resolve().parents[3] / "layouts" / "shortcodes" / "package-install.html"
)


def _source() -> str:
    return _SHORTCODE_PATH.read_text(encoding="utf-8")


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


def test_never_fabricates_an_install_command_when_unpublished():
    """The unpublished branch must render a notice, not a specific command --
    this is the mechanical enforcement of root cause 1 from the governing
    plan (a generation event must never guess a command for an unconfirmed
    package)."""
    src = _source()
    assert "not yet published" in src
    # The unpublished branch must come before any registry-specific command
    # branch in source order, so it's reached first for verification.published=false.
    unpublished_idx = src.index("not yet published")
    pypi_idx = src.index('eq $entry.registry_type "pypi"')
    assert unpublished_idx < pypi_idx
