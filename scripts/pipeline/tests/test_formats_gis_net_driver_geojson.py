"""Regression test: GeoJsonDriver's real GeoJSON format must be extracted
when running the format extractor against the gis/net clone cache.

Root cause (found live 2026-09-25, bootstrapping gis/net knowledge --
MT074-2026-09-25-GIS-NET-LAUNCH-AND-READINESS-GATE-HARDENING):

  Two independent gaps, each alone sufficient to drop the real GeoJSON
  format entry:

  1. detect_formats()'s importer_pattern (the class-name-suffix heuristic
     that recognizes Importer/Exporter/Reader/Writer/Loader/Saver/
     Serializer/Device/Renderer classes as format handlers) had no "Driver"
     alternative -- the GIS-domain naming idiom (OGR/GDAL-style: a driver
     class exposes both read and write), confirmed live via
     Aspose.GIS.FOSS/GeoJsonDriver.cs (CanCreateLayers=true, CanOpenLayers=
     true, CanCreateDatasets=true -- a real, non-stub read+write handler).
     WktWriter.cs's "Writer" suffix was correctly recognized by the
     pre-existing pattern; GeoJsonDriver.cs's "Driver" suffix was not.

  2. Even after adding "Driver", _validate_formats()'s CamelCase compound-
     word false-positive filter (_CAMELCASE_RE, ST-142) independently
     rejected the resulting "GeoJson" name -- indistinguishable, by that
     heuristic alone, from a genuine compound-word false positive like
     "ChartXml". GeoJSON (RFC 7946) is one real, singular format name, not
     two concepts. Fixed by adding "geojson" to
     _CAMELCASE_FALSE_POSITIVE_EXEMPT, the same mechanism already used for
     "threemf" (3MF, the 3D Manufacturing Format).

This test runs scout.py end-to-end against the real gis/net clone cache and
verifies both the real Wkt entry (already correctly extracted before this
fix) and the real GeoJson entry (previously silently dropped) are present.
"""
import json
import os
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

_REPO_ROOT = Path(__file__).resolve().parent.parent.parent.parent
_GIS_NET_CACHE = _REPO_ROOT / "runs" / ".clone_cache" / "aspose_gis_net"
_GIS_NET_HAS_SOURCES = (
    bool(list(_GIS_NET_CACHE.rglob("*.cs"))[:1])
    if _GIS_NET_CACHE.exists()
    else False
)
_SCOUT_SCRIPT = _REPO_ROOT / "scripts" / "pipeline" / "commands" / "knowledge" / "scout.py"


@unittest.skipUnless(
    _GIS_NET_HAS_SOURCES,
    "Clone cache absent or empty — run /repo-scout gis net first",
)
class TestGisNetFormatExtraction(unittest.TestCase):
    """WktWriter's Wkt and GeoJsonDriver's GeoJson must both be extracted."""

    @classmethod
    def setUpClass(cls):
        cls._tmpdir = tempfile.mkdtemp(prefix="scout_gis_net_fmt_test_")
        env = {**os.environ, "PYTHONPATH": str(_REPO_ROOT / "scripts" / "pipeline")}
        result = subprocess.run(
            [
                sys.executable,
                str(_SCOUT_SCRIPT),
                "gis",
                "net",
                str(_GIS_NET_CACHE),
                cls._tmpdir,
            ],
            capture_output=True,
            text=True,
            encoding="utf-8",
            env=env,
        )
        cls._scout_returncode = result.returncode
        cls._scout_stderr = result.stderr
        formats_path = Path(cls._tmpdir) / "formats.json"
        if formats_path.exists():
            cls._formats = json.loads(formats_path.read_text(encoding="utf-8"))
        else:
            cls._formats = []
        cls._by_name = {f["format"].lower(): f for f in cls._formats}

    def test_scout_exits_zero(self):
        self.assertEqual(
            self._scout_returncode, 0,
            f"scout.py exited {self._scout_returncode}:\n{self._scout_stderr}",
        )

    def test_wkt_present_export_direction(self):
        self.assertIn("wkt", self._by_name, f"formats.json: {self._formats}")
        self.assertEqual(self._by_name["wkt"]["direction"], "export")

    def test_geojson_present_not_silently_dropped(self):
        """The exact regression: GeoJsonDriver's real GeoJSON format must
        survive both the "Driver" suffix-recognition gap and the CamelCase
        compound-word false-positive filter."""
        self.assertIn(
            "geojson", self._by_name,
            f"'GeoJson' format entry missing — regression of the Driver-suffix "
            f"or CamelCase-exemption fix: {self._formats}",
        )
