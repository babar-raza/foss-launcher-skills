"""Regression tests for format_truth.py's H-3 fix
(MT074-2026-09-25-GIS-NET-LAUNCH-AND-READINESS-GATE-HARDENING).

Root incident: gis/net's placeholder products page claims Shapefile/GeoJSON/
KML/GPX/File-Geodatabase support, while the real repo (confirmed via clone
and a real scout run) only implements WKT + GeoJSON. Before this fix, the
evaluator's tokenizer (_FORMAT_TOKEN_RE / _KNOWN_EXTENSIONS) had zero
geospatial tokens at all -- it could not even recognize "Shapefile"/"KML"/
"GPX"/"GeoJSON" as format words, so it had no way to compare the claim
against formats.json, canonical/grade-affecting evaluator or not.

Two independent parts:
1. Static baseline extension (shp/shapefile/kml/kmz/gpx/geojson/wkt/gml) --
   what lets an OVER-claimed format the product does NOT have be recognized
   as a token worth checking in the first place.
2. Per-product-dynamic union with the product's own formats.json keys --
   durability for a future new-domain product's format that isn't yet in the
   static baseline at all.
"""
from __future__ import annotations

import json
import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parent.parent.parent))

from content_eval.evaluators import format_truth as _ft
from content_eval.evaluators.format_truth import FormatTruthEvaluator
from content_eval.models import Page


def _write_formats(tmp_path, family, platform, entries):
    merged_dir = tmp_path / family / platform / "merged"
    merged_dir.mkdir(parents=True, exist_ok=True)
    (merged_dir / "formats.json").write_text(json.dumps(entries), encoding="utf-8")


def _page(family, platform, prose_lines, layout="family"):
    text = "\n".join(t for _, t in prose_lines)
    return Page(
        filepath=Path(f"content/products.aspose.org/en/{family}/_index.md"),
        raw_text=text,
        frontmatter={"title": "Test", "layout": layout},
        body=text,
        prose_lines=prose_lines,
        family=family,
        platform=platform,
        subdomain="products",
        page_role="products",
    )


class TestGeospatialTokenRecognition:
    """Part 1: static baseline extension."""

    def test_geojson_wkt_recognized_as_tokens(self):
        mentions = _ft._extract_format_mentions("Supports WKT and GeoJSON export.")
        exts = {m[0] for m in mentions}
        assert "wkt" in exts
        assert "geojson" in exts

    def test_shapefile_kml_gpx_recognized_as_tokens(self):
        mentions = _ft._extract_format_mentions(
            "Read, write, and convert Shapefile, GeoJSON, KML, and GPX."
        )
        exts = {m[0] for m in mentions}
        assert {"shapefile", "geojson", "kml", "gpx"} <= exts


class TestGisNetOverclaimDetection:
    """End-to-end: the real gis/net scenario -- a page claiming Shapefile/
    KML/GPX support that the real, scouted formats.json does not have."""

    def test_overclaimed_formats_produce_findings(self, tmp_path):
        _ft.configure(knowledge_root=tmp_path)
        # Real gis/net shape: only Wkt (export) and GeoJson (import) exist.
        _write_formats(tmp_path, "gis", "net", [
            {"format": "Wkt", "direction": "export"},
            {"format": "GeoJson", "direction": "import"},
        ])
        page = _page("gis", "net", [
            (1, "Aspose.GIS FOSS reads and writes Shapefile, GeoJSON, KML, and GPX."),
        ])
        try:
            findings = FormatTruthEvaluator().evaluate(page, knowledge=None)
        finally:
            _ft.configure()
        # Before this fix: zero findings (the tokenizer never even saw these words).
        assert len(findings) > 0
        flagged = {f.message for f in findings}
        # At least one finding must actually be about the overclaimed formats,
        # not just an unrelated WARN.
        assert any(
            "shapefile" in d.lower() or "kml" in d.lower() or "gpx" in d.lower()
            for d in flagged
        ), flagged

    def test_correctly_claimed_formats_produce_no_overclaim_finding(self, tmp_path):
        """Green counterpart: claiming only what the product really has must
        not itself be flagged as an overclaim."""
        _ft.configure(knowledge_root=tmp_path)
        _write_formats(tmp_path, "gis", "net", [
            {"format": "Wkt", "direction": "export"},
            {"format": "GeoJson", "direction": "import"},
        ])
        page = _page("gis", "net", [
            (1, "Aspose.GIS FOSS reads GeoJSON and writes WKT."),
        ])
        try:
            findings = FormatTruthEvaluator().evaluate(page, knowledge=None)
        finally:
            _ft.configure()
        # Wkt is export-only and claimed as "writes" (export) -- consistent.
        # GeoJson is import-only and claimed as "reads" (import) -- consistent.
        overclaim_findings = [
            f for f in findings
            if "unknown" not in f.message.lower()  # unrelated categories are fine
        ]
        assert overclaim_findings == [] or all(
            "geojson" not in f.message.lower() and "wkt" not in f.message.lower()
            for f in overclaim_findings
        )


class TestPerProductDynamicTokens:
    """Part 2: a future new-domain format not yet in the static baseline at
    all must still be recognized once it's in the product's own formats.json."""

    def test_novel_format_not_in_static_baseline_is_recognized_when_in_formats_json(self):
        mentions_without = _ft._extract_format_mentions("Supports the Zorb format.")
        assert "zorb" not in {m[0] for m in mentions_without}

        mentions_with = _ft._extract_format_mentions(
            "Supports the Zorb format.", extra_tokens=frozenset({"zorb"})
        )
        assert "zorb" in {m[0] for m in mentions_with}

    def test_static_baseline_unaffected_by_empty_extra_tokens(self):
        """Backward compatible: no extra_tokens arg must behave exactly as before."""
        mentions = _ft._extract_format_mentions("Exports to PDF.")
        assert "pdf" in {m[0] for m in mentions}

    def test_format_token_re_for_caches_by_frozenset(self):
        """Same extra_tokens set must return the identical cached pattern
        object (functools.lru_cache), not recompile every call."""
        a = _ft._format_token_re_for(frozenset({"geojson"}))
        b = _ft._format_token_re_for(frozenset({"geojson"}))
        assert a is b
