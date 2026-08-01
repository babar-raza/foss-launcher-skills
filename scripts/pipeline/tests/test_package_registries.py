"""
Tests for scripts/pipeline/lib/package_registries/ (Mission
MT015-2026-07-30-PACKAGE-REGISTRY, TC-MT015-04).

All tests use an injected fake `fetch` callable -- zero live network calls,
per this repo's own CI convention (no precedent anywhere in this repo for
shelling out to a live external HTTP endpoint from pytest) and per this
mission's own fail-closed design requirement (a real API's flakiness must
never make a test flaky).
"""

import sys
from pathlib import Path

_LIB_DIR = Path(__file__).resolve().parents[1] / "lib"
if str(_LIB_DIR) not in sys.path:
    sys.path.insert(0, str(_LIB_DIR))

from package_registries import CheckResult, FetchResponse, apply_debounce, is_corroborated_match  # noqa: E402
from package_registries import pypi, npm, nuget, go, cargo  # noqa: E402


def _fake_fetch(status_code: int, body: bytes = b""):
    def _fetch(url: str):
        return FetchResponse(status_code=status_code, body=body)
    return _fetch


def _fake_fetch_connection_error():
    def _fetch(url: str):
        return None
    return _fetch


def _fake_fetch_by_url(mapping: dict):
    """mapping: {url_substring: (status_code, body)} -- first matching
    substring wins; unmatched URLs get a 404."""
    def _fetch(url: str):
        for substr, (status_code, body) in mapping.items():
            if substr in url:
                return FetchResponse(status_code=status_code, body=body)
        return FetchResponse(status_code=404, body=b"")
    return _fetch


class TestPyPiAdapter:
    def test_published(self):
        body = b'{"info": {"author": "Aspose", "maintainer": null}}'
        result = pypi.check_published({"name": "aspose-pdf-foss"}, fetch=_fake_fetch(200, body))
        assert result.published is True
        assert result.ambiguous is False
        assert result.verified_owner == "Aspose"
        assert "pypi.org" in result.evidence_url

    def test_not_published(self):
        result = pypi.check_published({"name": "aspose-pdf-foss"}, fetch=_fake_fetch(404))
        assert result.published is False
        assert result.ambiguous is False

    def test_ambiguous_on_server_error(self):
        result = pypi.check_published({"name": "aspose-pdf-foss"}, fetch=_fake_fetch(503))
        assert result.published is False
        assert result.ambiguous is True

    def test_ambiguous_on_connection_error(self):
        result = pypi.check_published({"name": "aspose-pdf-foss"}, fetch=_fake_fetch_connection_error())
        assert result.published is False
        assert result.ambiguous is True

    def test_ambiguous_on_malformed_json(self):
        result = pypi.check_published({"name": "aspose-pdf-foss"}, fetch=_fake_fetch(200, b"not json"))
        assert result.published is False
        assert result.ambiguous is True


class TestNpmAdapter:
    def test_published(self):
        body = b'{"maintainers": [{"name": "asposefoss"}]}'
        result = npm.check_published({"name": "@asposefoss/pdf"}, fetch=_fake_fetch(200, body))
        assert result.published is True
        assert result.verified_owner == "asposefoss"

    def test_not_published(self):
        result = npm.check_published({"name": "@asposefoss/pdf"}, fetch=_fake_fetch(404))
        assert result.published is False
        assert result.ambiguous is False

    def test_ambiguous_on_server_error(self):
        result = npm.check_published({"name": "@asposefoss/pdf"}, fetch=_fake_fetch(500))
        assert result.ambiguous is True

    def test_scoped_name_url_encoded(self):
        captured = {}
        def _fetch(url):
            captured["url"] = url
            return FetchResponse(status_code=404, body=b"")
        npm.check_published({"name": "@asposefoss/pdf"}, fetch=_fetch)
        assert "%40asposefoss%2Fpdf" in captured["url"]


class TestNuGetAdapter:
    def test_published(self):
        result = nuget.check_published({"name": "Aspose.Words.FOSS"}, fetch=_fake_fetch(200, b'{"versions":["1.0.0"]}'))
        assert result.published is True
        assert result.ambiguous is False

    def test_not_published(self):
        result = nuget.check_published({"name": "Aspose.Words.FOSS"}, fetch=_fake_fetch(404))
        assert result.published is False
        assert result.ambiguous is False

    def test_ambiguous_on_connection_error(self):
        result = nuget.check_published({"name": "Aspose.Words.FOSS"}, fetch=_fake_fetch_connection_error())
        assert result.ambiguous is True

    def test_url_is_lowercased(self):
        captured = {}
        def _fetch(url):
            captured["url"] = url
            return FetchResponse(status_code=404, body=b"")
        nuget.check_published({"name": "Aspose.Words.FOSS"}, fetch=_fetch)
        assert "aspose.words.foss" in captured["url"]
        assert "Aspose.Words.FOSS" not in captured["url"]


class TestGoAdapter:
    def test_published(self):
        result = go.check_published(
            {"module_path": "github.com/aspose-pdf-foss/aspose-pdf-foss-for-go"},
            fetch=_fake_fetch(200, b"v1.0.0\nv1.0.1\n"),
        )
        assert result.published is True
        assert result.ambiguous is False

    def test_not_published_404(self):
        result = go.check_published(
            {"module_path": "github.com/aspose-pdf-foss/aspose-pdf-foss-for-go"},
            fetch=_fake_fetch(404),
        )
        assert result.published is False
        assert result.ambiguous is False

    def test_not_published_410_gone(self):
        result = go.check_published(
            {"module_path": "github.com/aspose-pdf-foss/aspose-pdf-foss-for-go"},
            fetch=_fake_fetch(410),
        )
        assert result.published is False
        assert result.ambiguous is False

    def test_ambiguous_on_empty_200_body(self):
        result = go.check_published(
            {"module_path": "github.com/aspose-pdf-foss/aspose-pdf-foss-for-go"},
            fetch=_fake_fetch(200, b""),
        )
        assert result.ambiguous is True

    def test_mixed_case_module_path_is_escaped_before_the_proxy_request(self):
        """Real bug found 2026-08-01 (TC-MT018-06): cells/go's real module
        path has mixed case (github.com/aspose-cells-foss/Aspose.Cells-FOSS-for-Go/v26)
        and returned a false-negative 404 before this was fixed -- the Go
        module proxy protocol requires every uppercase letter escaped as
        '!' + lowercase."""
        captured = {}

        def _fetch(url):
            captured["url"] = url
            return FetchResponse(status_code=200, body=b"v26.7.0\nv26.7.1\n")

        result = go.check_published(
            {"module_path": "github.com/aspose-cells-foss/Aspose.Cells-FOSS-for-Go/v26"},
            fetch=_fetch,
        )
        assert result.published is True
        assert "!aspose.!cells-!f!o!s!s-for-!go" in captured["url"]
        # project_url/candidate_name stay in the original, human-readable form
        assert result.project_url == "https://github.com/aspose-cells-foss/Aspose.Cells-FOSS-for-Go/v26"
        assert result.candidate_name == "github.com/aspose-cells-foss/Aspose.Cells-FOSS-for-Go/v26"

    def test_all_lowercase_module_path_is_unchanged(self):
        """Backward-compat: the common all-lowercase case must produce the
        exact same URL as before this fix (no escaping needed)."""
        captured = {}

        def _fetch(url):
            captured["url"] = url
            return FetchResponse(status_code=200, body=b"v1.0.0\n")

        go.check_published({"module_path": "github.com/aspose-pdf-foss/aspose-pdf-foss-for-go"}, fetch=_fetch)
        assert captured["url"] == "https://proxy.golang.org/github.com/aspose-pdf-foss/aspose-pdf-foss-for-go/@v/list"


class TestCargoAdapter:
    """crates.io adapter (TC-MT015-09) -- built alongside /package-publish-watch
    since RUST-CRATESIO-001 explicitly names this gap and TC-MT015-04 covered
    only pypi/nuget/npm/go."""

    def test_published(self):
        body = b'{"crate": {"id": "aspose-cells-foss-rust"}}'
        result = cargo.check_published({"name": "aspose-cells-foss-rust"}, fetch=_fake_fetch(200, body))
        assert result.published is True
        assert result.ambiguous is False
        assert result.verified_owner == "aspose-cells-foss-rust"
        assert "crates.io" in result.evidence_url

    def test_not_published(self):
        result = cargo.check_published({"name": "aspose-cells-foss-rust"}, fetch=_fake_fetch(404))
        assert result.published is False
        assert result.ambiguous is False

    def test_ambiguous_on_server_error(self):
        result = cargo.check_published({"name": "aspose-cells-foss-rust"}, fetch=_fake_fetch(503))
        assert result.published is False
        assert result.ambiguous is True

    def test_ambiguous_on_connection_error(self):
        result = cargo.check_published({"name": "aspose-cells-foss-rust"}, fetch=_fake_fetch_connection_error())
        assert result.published is False
        assert result.ambiguous is True

    def test_ambiguous_on_malformed_json(self):
        result = cargo.check_published({"name": "aspose-cells-foss-rust"}, fetch=_fake_fetch(200, b"not json"))
        assert result.published is False
        assert result.ambiguous is True


class TestDebounce:
    """Rerun-consistency requirement: a single ambiguous or transient result
    must never flip live published state -- only 2 consecutive agreeing
    published=True results may."""

    def test_single_published_result_does_not_flip(self):
        counter, should_flip = apply_debounce(0, CheckResult(published=True, ambiguous=False, evidence_url="u", method="m"))
        assert counter == 1
        assert should_flip is False

    def test_two_consecutive_published_results_flip(self):
        counter, _ = apply_debounce(0, CheckResult(published=True, ambiguous=False, evidence_url="u", method="m"))
        counter, should_flip = apply_debounce(counter, CheckResult(published=True, ambiguous=False, evidence_url="u", method="m"))
        assert counter == 2
        assert should_flip is True

    def test_ambiguous_result_never_advances_counter_or_flips(self):
        counter, should_flip = apply_debounce(1, CheckResult(published=False, ambiguous=True, evidence_url="u", method="m"))
        assert counter == 1  # unchanged, not reset, not advanced
        assert should_flip is False

    def test_flapping_ambiguous_then_published_requires_two_full_agreements(self):
        """A flapping API (error, then success, then error, then success) must
        never accidentally accumulate credit toward a flip."""
        counter = 0
        counter, flip1 = apply_debounce(counter, CheckResult(published=True, ambiguous=False, evidence_url="u", method="m"))
        assert flip1 is False
        counter, flip2 = apply_debounce(counter, CheckResult(published=False, ambiguous=True, evidence_url="u", method="m"))
        assert flip2 is False
        assert counter == 1  # ambiguous did not reset the real progress either
        counter, flip3 = apply_debounce(counter, CheckResult(published=True, ambiguous=False, evidence_url="u", method="m"))
        assert flip3 is True
        assert counter == 2

    def test_not_published_resets_counter(self):
        counter, _ = apply_debounce(0, CheckResult(published=True, ambiguous=False, evidence_url="u", method="m"))
        assert counter == 1
        counter, should_flip = apply_debounce(counter, CheckResult(published=False, ambiguous=False, evidence_url="u", method="m"))
        assert counter == 0
        assert should_flip is False


class TestIsCorroboratedMatch:
    """Mission MT018-2026-08-01-PACKAGE-IDENTITY-COVERAGE identity-verification
    rule (user-mandated): foss-substring OR corroborated project_url match."""

    def test_foss_in_name_is_always_accepted(self):
        assert is_corroborated_match("aspose-cells-foss", None, "anything") is True
        assert is_corroborated_match("Aspose.Slides.Foss", None, "anything") is True

    def test_non_foss_name_with_matching_project_url_is_accepted(self):
        """Real case: PyPI's aspose-note (no 'foss') IS the genuine FOSS
        package -- project_urls point exactly to the FOSS GitHub org."""
        assert is_corroborated_match(
            "aspose-note",
            "https://github.com/aspose-note-foss/Aspose.Note-FOSS-for-Python",
            "aspose-note-foss",
        ) is True

    def test_non_foss_name_with_unrelated_project_url_is_rejected(self):
        """Real case: PyPI's aspose-page is an unrelated COMMERCIAL package --
        no foss substring, no matching project URL -- must be rejected."""
        assert is_corroborated_match(
            "aspose-page",
            "https://products.aspose.com/page/python-net/",
            "aspose-page-foss",
        ) is False

    def test_non_foss_name_with_no_project_url_is_rejected(self):
        assert is_corroborated_match("aspose-page", None, "aspose-page-foss") is False


class TestProjectUrlExtraction:
    """Each adapter must populate CheckResult.project_url from its real API
    response so is_corroborated_match() has evidence to work with."""

    def test_pypi_extracts_project_url_from_project_urls(self):
        body = b'{"info": {"author": "Aspose", "project_urls": {"Repository": "https://github.com/aspose-note-foss/x"}}}'
        result = pypi.check_published({"name": "aspose-note"}, fetch=_fake_fetch(200, body))
        assert result.project_url == "https://github.com/aspose-note-foss/x"

    def test_pypi_falls_back_to_home_page(self):
        body = b'{"info": {"author": "Aspose", "home_page": "https://example.com/repo"}}'
        result = pypi.check_published({"name": "aspose-x"}, fetch=_fake_fetch(200, body))
        assert result.project_url == "https://example.com/repo"

    def test_npm_extracts_project_url_from_repository(self):
        body = b'{"maintainers": [{"name": "asposefoss"}], "repository": {"url": "git+https://github.com/aspose-x-foss/x.git"}}'
        result = npm.check_published({"name": "@asposefoss/x"}, fetch=_fake_fetch(200, body))
        assert "github.com/aspose-x-foss" in result.project_url

    def test_cargo_extracts_project_url_from_repository(self):
        body = b'{"crate": {"id": "aspose-cells-foss-rust", "repository": "https://github.com/aspose-cells-foss/x"}}'
        result = cargo.check_published({"name": "aspose-cells-foss-rust"}, fetch=_fake_fetch(200, body))
        assert result.project_url == "https://github.com/aspose-cells-foss/x"

    def test_go_project_url_is_the_module_path_itself(self):
        result = go.check_published(
            {"module_path": "github.com/aspose-pdf-foss/aspose-pdf-foss-for-go"},
            fetch=_fake_fetch(200, b"v1.0.0\n"),
        )
        assert result.project_url == "https://github.com/aspose-pdf-foss/aspose-pdf-foss-for-go"

    def test_nuget_extracts_authors_and_project_url_from_registration_api(self):
        reg_body = (
            b'{"items": [{"items": [{"catalogEntry": '
            b'{"authors": "Aspose", "projectUrl": "https://github.com/aspose-note-foss/x"}}]}]}'
        )
        fetch = _fake_fetch_by_url({
            "v3-flatcontainer": (200, b'{"versions": ["26.1.0"]}'),
            "registration5-semver1": (200, reg_body),
        })
        result = nuget.check_published({"name": "Aspose.Note.FOSS"}, fetch=fetch)
        assert result.verified_owner == "Aspose"
        assert result.project_url == "https://github.com/aspose-note-foss/x"

    def test_nuget_registration_failure_does_not_break_published_detection(self):
        """If the registration API call fails, the package is still correctly
        reported published (from the flatcontainer check alone) -- just
        without owner/project_url metadata."""
        fetch = _fake_fetch_by_url({
            "v3-flatcontainer": (200, b'{"versions": ["26.1.0"]}'),
            "registration5-semver1": (503, b""),
        })
        result = nuget.check_published({"name": "Aspose.Note.FOSS"}, fetch=fetch)
        assert result.published is True
        assert result.verified_owner is None
        assert result.project_url is None


class TestSearchFallback:
    """When a naming-convention guess 404s, search() finds real,
    non-conforming packages (the aspose-note case) via each registry's
    actual search API (pypi: variant guessing, since PyPI has no free-text
    search API; npm/nuget/cargo: real search endpoints)."""

    def test_pypi_search_finds_first_resolving_variant(self):
        body = b'{"info": {"author": "Aspose", "project_urls": {"Repository": "https://github.com/aspose-note-foss/x"}}}'
        fetch = _fake_fetch_by_url({"pypi/aspose-note/json": (200, body)})
        results = pypi.search("note", fetch=fetch)
        assert len(results) == 1
        assert results[0].candidate_name == "aspose-note"
        assert results[0].published is True

    def test_pypi_search_returns_empty_when_no_variant_resolves(self):
        fetch = _fake_fetch(404)
        results = pypi.search("nonexistent", fetch=fetch)
        assert results == []

    def test_npm_search_filters_to_aspose_related_hits(self):
        search_body = b'{"objects": [{"package": {"name": "@aspose/cells-foss"}}, {"package": {"name": "unrelated-pkg"}}]}'
        pkg_body = b'{"maintainers": [{"name": "asposefoss"}], "repository": {"url": "https://github.com/aspose-cells-foss/x"}}'
        fetch = _fake_fetch_by_url({
            "-/v1/search": (200, search_body),
            "%40aspose%2Fcells-foss": (200, pkg_body),
        })
        results = npm.search("cells", fetch=fetch)
        assert len(results) == 1
        assert results[0].candidate_name == "@aspose/cells-foss"

    def test_nuget_search_filters_to_aspose_related_hits(self):
        search_body = b'{"data": [{"id": "Aspose.Cells.FOSS"}, {"id": "UnrelatedPackage"}]}'
        flat_body = b'{"versions": ["26.1.0"]}'
        fetch = _fake_fetch_by_url({
            "azuresearch": (200, search_body),
            "v3-flatcontainer": (200, flat_body),
            "registration5-semver1": (503, b""),
        })
        results = nuget.search("cells", fetch=fetch)
        assert len(results) == 1
        assert results[0].candidate_name == "Aspose.Cells.FOSS"

    def test_cargo_search_filters_to_aspose_related_hits(self):
        search_body = b'{"crates": [{"name": "aspose-cells-foss-rust"}, {"name": "unrelated"}]}'
        crate_body = b'{"crate": {"id": "aspose-cells-foss-rust", "repository": "https://github.com/aspose-cells-foss/x"}}'
        fetch = _fake_fetch_by_url({
            "crates.io/api/v1/crates?q=": (200, search_body),
            "crates.io/api/v1/crates/aspose-cells-foss-rust": (200, crate_body),
        })
        results = cargo.search("cells", fetch=fetch)
        assert len(results) == 1
        assert results[0].candidate_name == "aspose-cells-foss-rust"
