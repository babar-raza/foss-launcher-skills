"""HARDEN-words-net: MAX_FILES truncation must never be silent.

words/net (Aspose.Words FOSS for .NET) was the first product to ever exceed
the scout's file-collection cap: 3,167 source files under its package root
against a MAX_FILES=500 ceiling nobody had revisited since (every other
product measured at the time — pdf/net 385, slides/net 297, cells/net 219 —
was comfortably under it). ~84% of the product's source files were silently
dropped from extraction, and the existing skip-rate/parse-error-rate quality
monitoring in extraction/scout.py never caught it, because those checks
operate on `files_attempted`, which is already the POST-cap count — a
capped product and one that fit comfortably inside the cap produced
identical-looking reports.

This test guards two things: (1) the cap itself was raised with real
headroom (8000, vs. words/net's 3167), and (2) any FUTURE product that
exceeds even that ceiling can never again look identical to one that didn't
— capping must always be visible in the returned stats and in
scout_report.json, and must always log a loud warning.
"""
from __future__ import annotations

import logging

import extraction.tree_helpers as tree_helpers
from extraction.tree_helpers import _collect_source_files


def _make_files(tmp_path, count, ext=".cs"):
    for i in range(count):
        (tmp_path / f"Class{i:04d}{ext}").write_text("public class C {}", encoding="utf-8")


def test_max_files_env_override(monkeypatch):
    """SCOUT_MAX_FILES lets a future outlier product be raised without a code
    edit + redeploy — re-import to pick up the env var like any fresh process
    would (module-level constants are read once at import time)."""
    import importlib

    monkeypatch.setenv("SCOUT_MAX_FILES", "12345")
    try:
        importlib.reload(tree_helpers)
        assert tree_helpers.MAX_FILES == 12345
    finally:
        monkeypatch.delenv("SCOUT_MAX_FILES", raising=False)
        importlib.reload(tree_helpers)  # restore the real default for later tests


def test_max_files_raised_with_real_headroom_over_words_net():
    """words/net measured 3,167 source files under its package root — the cap
    must comfortably exceed that today, not just barely clear it."""
    assert tree_helpers.MAX_FILES >= 3167 * 2, (
        f"MAX_FILES={tree_helpers.MAX_FILES} no longer has real headroom over "
        "words/net's measured size (3,167) -- revisit before another product "
        "silently hits this cap again"
    )


def test_under_cap_returns_all_files_uncapped(tmp_path, monkeypatch):
    monkeypatch.setattr(tree_helpers, "MAX_FILES", 100)
    _make_files(tmp_path, 10)

    stats: dict = {}
    files = _collect_source_files(tmp_path, ".cs", stats=stats)

    assert len(files) == 10
    assert stats["candidates_found"] == 10
    assert stats["files_capped"] is False


def test_over_cap_truncates_and_reports_truncation(tmp_path, monkeypatch, caplog):
    monkeypatch.setattr(tree_helpers, "MAX_FILES", 3)
    _make_files(tmp_path, 5)

    stats: dict = {}
    with caplog.at_level(logging.WARNING, logger="extraction.tree_helpers"):
        files = _collect_source_files(tmp_path, ".cs", stats=stats)

    assert len(files) == 3, "must still return exactly MAX_FILES files, not silently more/fewer"
    assert stats["candidates_found"] == 5, "true pre-cap count must be reported, not the capped one"
    assert stats["files_capped"] is True
    assert any("MAX_FILES cap reached" in r.message for r in caplog.records), (
        "truncation must log a warning -- this is exactly what was missing "
        "when words/net silently lost 84% of its source files"
    )


def test_stats_param_is_optional_backward_compatible(tmp_path, monkeypatch):
    """Existing callers that don't pass stats= must see zero behavior change."""
    monkeypatch.setattr(tree_helpers, "MAX_FILES", 2)
    _make_files(tmp_path, 5)

    files = _collect_source_files(tmp_path, ".cs")  # no stats= at all

    assert len(files) == 2


def test_extract_api_surface_scout_report_carries_truncation_fact(tmp_path, monkeypatch):
    """The durable artifact (scout_report.json in real runs) must carry the
    same truncation fact as the in-memory stats dict -- not just a log line
    that vanishes once the run completes."""
    import extraction.api_surface as api_surface

    monkeypatch.setattr(tree_helpers, "MAX_FILES", 2)
    _make_files(tmp_path, 4)

    parser = tree_helpers.get_parser("csharp")
    _classes, _claims, _files, _pkgs, scout_report = api_surface.extract_api_surface(
        parser, "csharp", tmp_path, tmp_path, "test-family",
    )

    assert scout_report["files_attempted"] == 2, (
        "files_attempted reflects the post-cap count -- by itself this looks "
        "identical whether or not 2 more files existed, which is exactly the "
        "blind spot these two new fields close"
    )
    assert scout_report["total_source_files_found"] == 4
    assert scout_report["files_capped"] is True


def test_extract_api_surface_scout_report_not_capped_when_under_limit(tmp_path):
    import extraction.api_surface as api_surface

    _make_files(tmp_path, 3)
    parser = tree_helpers.get_parser("csharp")
    _classes, _claims, _files, _pkgs, scout_report = api_surface.extract_api_surface(
        parser, "csharp", tmp_path, tmp_path, "test-family",
    )

    assert scout_report["files_capped"] is False
    assert scout_report["total_source_files_found"] == 3


def test_header_ext_accumulation_counts_toward_total_and_cap(tmp_path, monkeypatch):
    """C++-style extraction collects a primary ext plus one or more header
    exts in the SAME cap budget. total_candidates must sum ALL of them (not
    just the primary ext), and the cap must apply across the combined set —
    this is the one code path with no prior direct test coverage."""
    monkeypatch.setattr(tree_helpers, "MAX_FILES", 5)
    _make_files(tmp_path, 3, ext=".cpp")
    _make_files(tmp_path, 4, ext=".h")
    _make_files(tmp_path, 2, ext=".hpp")
    # 3 + 4 + 2 = 9 candidates total, cap = 5

    stats: dict = {}
    files = _collect_source_files(tmp_path, ".cpp", [".h", ".hpp"], stats=stats)

    assert len(files) == 5, "must return exactly MAX_FILES files across the combined ext set"
    assert stats["candidates_found"] == 9, "must count ALL exts (primary + every header_ext), not just the primary one"
    assert stats["files_capped"] is True


def test_header_ext_accumulation_uncapped_when_combined_total_fits(tmp_path, monkeypatch):
    monkeypatch.setattr(tree_helpers, "MAX_FILES", 20)
    _make_files(tmp_path, 3, ext=".cpp")
    _make_files(tmp_path, 4, ext=".h")

    stats: dict = {}
    files = _collect_source_files(tmp_path, ".cpp", [".h"], stats=stats)

    assert len(files) == 7
    assert stats["candidates_found"] == 7
    assert stats["files_capped"] is False
