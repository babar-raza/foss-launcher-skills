"""
Tests for scripts/pipeline/lib/package_registries/ (Mission
MT015-2026-07-30-PACKAGE-REGISTRY, TC-MT015-04).

All tests use an injected fake `fetch` callable -- zero live network calls,
per this repo's own CI convention (no precedent anywhere in this repo for
shelling out to a live external HTTP endpoint from pytest) and per this
mission's own fail-closed design requirement (a real API's flakiness must
never make a test flaky).
"""

import json
import sys
from pathlib import Path

_LIB_DIR = Path(__file__).resolve().parents[1] / "lib"
if str(_LIB_DIR) not in sys.path:
    sys.path.insert(0, str(_LIB_DIR))

from package_registries import CheckResult, FetchResponse, apply_debounce, is_corroborated_match  # noqa: E402
from package_registries import pypi, npm, nuget, go, cargo, maven  # noqa: E402


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


class TestMavenAdapter:
    """MT075-T6: CheckResult-shaped shim over the same maven-metadata.xml
    approach commands.ops.publish_watcher.default_live_checker uses --
    exercised here through the shared fetch-injection convention so
    registry_watch.py can treat Maven like the other 5 registries."""

    _METADATA_XML = (
        b"<metadata><versioning><release>26.7.0</release>"
        b"<latest>26.7.0</latest></versioning></metadata>"
    )

    def test_published(self):
        result = maven.check_published(
            {"group_id": "org.aspose", "artifact_id": "aspose-cells-foss"},
            fetch=_fake_fetch(200, self._METADATA_XML),
        )
        assert result.published is True
        assert result.ambiguous is False
        assert result.version == "26.7.0"
        assert result.candidate_name == "aspose-cells-foss"

    def test_not_published_404(self):
        result = maven.check_published(
            {"group_id": "org.aspose", "artifact_id": "aspose-cells-foss"},
            fetch=_fake_fetch(404),
        )
        assert result.published is False
        assert result.ambiguous is False

    def test_ambiguous_on_connection_error(self):
        result = maven.check_published(
            {"group_id": "org.aspose", "artifact_id": "aspose-cells-foss"},
            fetch=_fake_fetch_connection_error(),
        )
        assert result.ambiguous is True

    def test_ambiguous_on_malformed_xml(self):
        result = maven.check_published(
            {"group_id": "org.aspose", "artifact_id": "aspose-cells-foss"},
            fetch=_fake_fetch(200, b"not xml at all"),
        )
        assert result.ambiguous is True

    def test_group_id_dots_become_path_segments(self):
        captured = {}

        def _fetch(url: str):
            captured["url"] = url
            return FetchResponse(status_code=404, body=b"")

        maven.check_published({"group_id": "org.aspose", "artifact_id": "aspose-cells-foss"}, fetch=_fetch)
        assert "org/aspose/aspose-cells-foss/maven-metadata.xml" in captured["url"]

    def test_search_filters_to_aspose_named_artifacts(self):
        body = json.dumps({
            "response": {"docs": [
                {"g": "org.aspose", "a": "aspose-cells-foss"},
                {"g": "org.other", "a": "unrelated-lib"},
            ]}
        }).encode("utf-8")

        def _fetch(url: str):
            if "solrsearch" in url:
                return FetchResponse(status_code=200, body=body)
            return FetchResponse(status_code=200, body=self._METADATA_XML)

        results = maven.search("cells", fetch=_fetch)
        assert len(results) == 1
        assert results[0].candidate_name == "aspose-cells-foss"


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
        exact same @v/list URL as before this fix (no escaping needed).
        Updated for Phase 1 (Mission MT066): check_published() now also
        fetches @latest for the live version, so this captures every URL
        fetched rather than assuming a single call."""
        captured = []

        def _fetch(url):
            captured.append(url)
            return FetchResponse(status_code=200, body=b"v1.0.0\n")

        go.check_published({"module_path": "github.com/aspose-pdf-foss/aspose-pdf-foss-for-go"}, fetch=_fetch)
        assert "https://proxy.golang.org/github.com/aspose-pdf-foss/aspose-pdf-foss-for-go/@v/list" in captured


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


class TestLiveVersionExtraction:
    """Mission MT066-2026-09-09-PACKAGE-INSTALL-RECONCILIATION, Phase 1: every
    registry now extracts a live version, not just Maven. All fixture-based,
    zero live network calls, same convention as every other class here."""

    def test_pypi_extracts_version_from_info(self):
        body = b'{"info": {"author": "Aspose", "version": "26.8.0"}}'
        result = pypi.check_published({"name": "aspose-pdf-foss"}, fetch=_fake_fetch(200, body))
        assert result.version == "26.8.0"

    def test_nuget_extracts_last_entry_of_versions_array(self):
        fetch = _fake_fetch_by_url({
            "v3-flatcontainer": (200, b'{"versions": ["26.1.0", "26.5.0", "26.8.0"]}'),
            "registration5-semver1": (503, b""),
        })
        result = nuget.check_published({"name": "Aspose.Words.FOSS"}, fetch=fetch)
        assert result.version == "26.8.0"

    def test_nuget_version_none_on_malformed_flatcontainer_body(self):
        """A parse failure on the versions array must not break published
        detection -- same isolation as the registration-metadata failure mode."""
        fetch = _fake_fetch_by_url({
            "v3-flatcontainer": (200, b"not json"),
            "registration5-semver1": (503, b""),
        })
        result = nuget.check_published({"name": "Aspose.Words.FOSS"}, fetch=fetch)
        assert result.published is True
        assert result.version is None

    def test_npm_extracts_version_from_dist_tags_latest(self):
        body = b'{"maintainers": [{"name": "asposefoss"}], "dist-tags": {"latest": "26.8.0"}}'
        result = npm.check_published({"name": "@asposefoss/pdf"}, fetch=_fake_fetch(200, body))
        assert result.version == "26.8.0"

    def test_go_extracts_version_from_latest_endpoint(self):
        fetch = _fake_fetch_by_url({
            "@v/list": (200, b"v26.7.0\nv26.8.0\n"),
            "@latest": (200, b'{"Version": "v26.8.0", "Time": "2026-08-01T00:00:00Z"}'),
        })
        result = go.check_published(
            {"module_path": "github.com/aspose-pdf-foss/aspose-pdf-foss-for-go"}, fetch=fetch,
        )
        assert result.published is True
        assert result.version == "v26.8.0"

    def test_go_version_none_when_latest_endpoint_fails(self):
        """A failed/malformed @latest call must not break published detection
        -- @v/list alone already established that."""
        fetch = _fake_fetch_by_url({
            "@v/list": (200, b"v26.7.0\n"),
            "@latest": (503, b""),
        })
        result = go.check_published(
            {"module_path": "github.com/aspose-pdf-foss/aspose-pdf-foss-for-go"}, fetch=fetch,
        )
        assert result.published is True
        assert result.version is None

    def test_cargo_extracts_max_version(self):
        body = b'{"crate": {"id": "aspose-cells-foss-rust", "max_version": "26.8.0", "newest_version": "26.7.0"}, "versions": []}'
        result = cargo.check_published({"name": "aspose-cells-foss-rust"}, fetch=_fake_fetch(200, body))
        assert result.version == "26.8.0"
        assert result.yanked is False

    def test_cargo_falls_back_to_newest_version_when_max_version_absent(self):
        body = b'{"crate": {"id": "aspose-cells-foss-rust", "newest_version": "26.7.0"}, "versions": []}'
        result = cargo.check_published({"name": "aspose-cells-foss-rust"}, fetch=_fake_fetch(200, body))
        assert result.version == "26.7.0"

    def test_cargo_detects_yanked_max_version(self):
        """A yanked version is discouraged, not gone -- must surface distinctly
        from published=False, never mistaken for a removal signal."""
        body = (
            b'{"crate": {"id": "aspose-cells-foss-rust", "max_version": "26.8.0"}, '
            b'"versions": [{"num": "26.8.0", "yanked": true}, {"num": "26.7.0", "yanked": false}]}'
        )
        result = cargo.check_published({"name": "aspose-cells-foss-rust"}, fetch=_fake_fetch(200, body))
        assert result.published is True
        assert result.version == "26.8.0"
        assert result.yanked is True

    def test_cargo_yanked_defaults_false_when_no_version_data(self):
        body = b'{"crate": {"id": "aspose-cells-foss-rust"}}'
        result = cargo.check_published({"name": "aspose-cells-foss-rust"}, fetch=_fake_fetch(200, body))
        assert result.version is None
        assert result.yanked is False


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

    def test_empty_expected_fragment_does_not_universally_match(self):
        """Mission MT066-2026-09-09-PACKAGE-INSTALL-RECONCILIATION, Phase 2:
        an empty expected_repo_fragment (e.g. a family missing from
        data/products.json) must never be treated as 'matches everything' --
        Python's `"" in s` is always True, which would silently defeat this
        entire safeguard for any caller that couldn't resolve a real fragment."""
        assert is_corroborated_match("aspose-page", "https://products.aspose.com/page/", "") is False


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


class TestFetchWithRetry:
    """default_fetch's transport policy, tested through an injected single-attempt
    fetch and an injected sleep (no live network, no monkeypatching urllib).

    Root cause this exists for (measured 2026-09-18, 50 sequential calls): api.nuget.org
    intermittently stalls at TCP connect (2-3 of 50 calls hit the 10s timeout), which
    the adapters faithfully report as `ambiguous`. Ambiguity is fail-closed and safe,
    but with no retry every stall costs the debounce a whole extra day."""

    def test_returns_first_success_without_sleeping(self):
        from package_registries import _fetch_with_retry
        slept = []
        calls = []

        def once(url):
            calls.append(url)
            return FetchResponse(200, b"ok")

        resp = _fetch_with_retry("u", once, attempts=2, sleep=slept.append)
        assert resp.status_code == 200 and calls == ["u"] and slept == []

    def test_retries_transport_failure_once_then_succeeds(self):
        from package_registries import _fetch_with_retry
        seq = iter([None, FetchResponse(200, b"ok")])
        slept = []
        resp = _fetch_with_retry("u", lambda url: next(seq), attempts=2, sleep=slept.append)
        assert resp.status_code == 200 and len(slept) == 1

    def test_retries_transient_status_codes(self):
        from package_registries import _fetch_with_retry
        for transient in (429, 500, 502, 503, 504):
            seq = iter([FetchResponse(transient, b""), FetchResponse(200, b"ok")])
            resp = _fetch_with_retry("u", lambda url: next(seq), attempts=2, sleep=lambda s: None)
            assert resp.status_code == 200, transient

    def test_never_retries_a_definitive_answer(self):
        """404/410 are the registry's real answer (package absent). Retrying would
        only add latency and could not change a correct result."""
        from package_registries import _fetch_with_retry
        for definitive in (200, 404, 410):
            calls = []

            def once(url, definitive=definitive):
                calls.append(1)
                return FetchResponse(definitive, b"")

            _fetch_with_retry("u", once, attempts=3, sleep=lambda s: None)
            assert len(calls) == 1, definitive

    def test_gives_up_after_attempts_and_reports_last_outcome(self):
        from package_registries import _fetch_with_retry
        calls = []

        def once(url):
            calls.append(1)
            return None

        assert _fetch_with_retry("u", once, attempts=2, sleep=lambda s: None) is None
        assert len(calls) == 2
        seq = iter([FetchResponse(503, b""), FetchResponse(503, b"")])
        resp = _fetch_with_retry("u", lambda url: next(seq), attempts=2, sleep=lambda s: None)
        assert resp.status_code == 503  # still the caller's 'ambiguous', never a fabricated success


class TestFetchOnceProtocolErrors:
    """A malformed/partial HTTP exchange (http.client.HTTPException subclasses such as
    IncompleteRead/BadStatusLine/LineTooLong) is NOT an OSError, so before this it
    escaped default_fetch and aborted the entire watcher run -- one bad response from
    one registry hid every other package's result."""

    def test_http_protocol_errors_map_to_none_not_raise(self):
        import http.client
        from package_registries import _classify_fetch_exception
        for exc in (http.client.IncompleteRead(b"x"), http.client.BadStatusLine("x"), http.client.LineTooLong("status line")):
            assert _classify_fetch_exception(exc) is None

    def test_unrelated_exceptions_still_propagate(self):
        import pytest
        from package_registries import _classify_fetch_exception
        with pytest.raises(KeyError):
            _classify_fetch_exception(KeyError("bug in the caller, not a network fault"))


class TestPlatformCompatible:
    """NuGet is the one registry shared by two platforms (net and cpp). A family-level
    search returns both; a name must be accepted only for the platform it belongs to."""

    def test_nuget_cpp_requires_cpp_marker(self):
        from package_registries import platform_compatible
        assert platform_compatible("nuget", "cpp", "Aspose.Slides.Cpp.FOSS")
        assert not platform_compatible("nuget", "cpp", "Aspose.Email.Foss")

    def test_nuget_net_rejects_cpp_packages(self):
        from package_registries import platform_compatible
        assert platform_compatible("nuget", "net", "Aspose.Slides.FOSS")
        assert not platform_compatible("nuget", "net", "Aspose.Slides.Cpp.FOSS")

    def test_other_registries_are_unconstrained(self):
        from package_registries import platform_compatible
        assert platform_compatible("pypi", "python", "aspose-page-foss")
        assert platform_compatible("npm", "typescript", "@asposefoss/pdf")
