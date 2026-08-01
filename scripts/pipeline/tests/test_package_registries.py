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

from package_registries import CheckResult, FetchResponse, apply_debounce  # noqa: E402
from package_registries import pypi, npm, nuget, go  # noqa: E402


def _fake_fetch(status_code: int, body: bytes = b""):
    def _fetch(url: str):
        return FetchResponse(status_code=status_code, body=body)
    return _fetch


def _fake_fetch_connection_error():
    def _fetch(url: str):
        return None
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
