"""Tests for scout completeness reporting (S1-6 fix).

Verifies that extract_api_surface() returns a scout_report as its 5th
element and that unreadable files are tracked in files_skipped.
"""
from __future__ import annotations

import os
import sys

import pytest

# ---------------------------------------------------------------------------
# Ensure pipeline root is on sys.path so bare ``from extraction...`` works.
# ---------------------------------------------------------------------------
_PIPELINE_ROOT = os.path.join(os.path.dirname(__file__), os.pardir)
if _PIPELINE_ROOT not in sys.path:
    sys.path.insert(0, os.path.abspath(_PIPELINE_ROOT))


@pytest.fixture()
def java_parser():
    from extraction.tree_helpers import get_parser
    return get_parser("java")


@pytest.fixture()
def python_parser():
    from extraction.tree_helpers import get_parser
    return get_parser("python")


class TestScoutReportIncludedInReturn:
    """extract_api_surface must return scout_report as 5th element."""

    def test_returns_five_elements(self, python_parser, tmp_path):
        pkg = tmp_path / "pkg"
        pkg.mkdir()
        (pkg / "__init__.py").write_text("")
        (pkg / "mod.py").write_text("class Foo:\n    pass\n")

        from extraction.api_surface import extract_api_surface
        result = extract_api_surface(python_parser, "python", pkg, tmp_path, "test")
        assert len(result) == 5, f"Expected 5-tuple, got {len(result)}-tuple"

    def test_scout_report_has_required_keys(self, python_parser, tmp_path):
        pkg = tmp_path / "pkg"
        pkg.mkdir()
        (pkg / "__init__.py").write_text("")
        (pkg / "mod.py").write_text("class Bar:\n    pass\n")

        from extraction.api_surface import extract_api_surface
        _, _, _, _, report = extract_api_surface(
            python_parser, "python", pkg, tmp_path, "test"
        )
        for key in ("files_attempted", "files_parsed", "files_skipped", "skip_reasons"):
            assert key in report, f"scout_report missing key '{key}'"

    def test_no_skips_when_all_files_readable(self, python_parser, tmp_path):
        pkg = tmp_path / "pkg"
        pkg.mkdir()
        (pkg / "__init__.py").write_text("")
        (pkg / "a.py").write_text("class A:\n    pass\n")
        (pkg / "b.py").write_text("class B:\n    pass\n")

        from extraction.api_surface import extract_api_surface
        _, _, _, _, report = extract_api_surface(
            python_parser, "python", pkg, tmp_path, "test"
        )
        assert report["files_attempted"] >= 2
        assert report["files_parsed"] == report["files_attempted"]
        assert report["files_skipped"] == []
        assert report["skip_reasons"] == {}


class TestSkipTrackingOnUnreadableFile:
    """Unreadable files must be tracked in scout_report.files_skipped."""

    @pytest.mark.skipif(
        sys.platform == "win32",
        reason="os.chmod cannot reliably remove read permission on Windows",
    )
    def test_unreadable_file_tracked(self, python_parser, tmp_path):
        pkg = tmp_path / "pkg"
        pkg.mkdir()
        (pkg / "__init__.py").write_text("")
        good = pkg / "good.py"
        good.write_text("class Good:\n    pass\n")
        bad = pkg / "bad.py"
        bad.write_text("class Bad:\n    pass\n")
        # Make file unreadable
        os.chmod(bad, 0o000)
        try:
            from extraction.api_surface import extract_api_surface
            _, _, scanned, _, report = extract_api_surface(
                python_parser, "python", pkg, tmp_path, "test"
            )
            assert len(report["files_skipped"]) >= 1
            skipped_basenames = [
                os.path.basename(f) for f in report["files_skipped"]
            ]
            assert "bad.py" in skipped_basenames
            assert report["files_parsed"] < report["files_attempted"]
            assert sum(report["skip_reasons"].values()) == len(report["files_skipped"])
        finally:
            os.chmod(bad, 0o644)
