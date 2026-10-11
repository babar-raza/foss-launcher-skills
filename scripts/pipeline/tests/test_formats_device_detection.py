"""Regression test: Device-class format detection in extraction/formats.py.

Root cause guarded (F1b-IMPL / Gap G8):
  The format extractor only detected SaveFormat/LoadFormat enum members and
  Importer/Exporter/Reader/Writer suffix classes.  Device-class outputs
  (e.g. TiffDevice, BmpDevice, PngDevice) were never extracted even though
  they represent real user-facing format output capabilities.

  For pdf/net: SaveFormat.Tiff has direction='enum_only'/'functional=false'
  (the FOSS library does not implement Document.Save(SaveFormat.Tiff)).
  But TiffDevice.Process(page, stream) IS implemented and exports TIFF.
  Without Device detection, capability_claim_check fires 29 false-positive
  FAILs on pages that correctly claim TIFF export support via TiffDevice.

Fix: importer_pattern extended with 'Device'; export direction check and
strip regex updated; 'page' added to _FALSE_POSITIVE_NAMES (blocks PageDevice
abstract base class).

This test runs scout.py end-to-end against the pdf/net clone cache and
verifies:
1. TIFF appears as an export entry (from TiffDevice.cs)
2. 'Page' does NOT appear as a format entry (PageDevice is abstract FP)
3. 'Image' and 'Document' do NOT appear (already in false-positive list)
"""
import json
import os
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

_REPO_ROOT = Path(__file__).resolve().parent.parent.parent.parent
_PDF_NET_CACHE = _REPO_ROOT / "runs" / ".clone_cache" / "aspose_pdf_net"
_PDF_NET_HAS_SOURCES = (
    bool(list(_PDF_NET_CACHE.rglob("*.cs"))[:1])
    if _PDF_NET_CACHE.exists()
    else False
)
_SCOUT_SCRIPT = _REPO_ROOT / "scripts" / "pipeline" / "commands" / "knowledge" / "scout.py"


@unittest.skipUnless(
    _PDF_NET_HAS_SOURCES,
    "Clone cache absent or empty — run /repo-scout pdf net first",
)
class TestPdfNetDeviceClassFormatDetection(unittest.TestCase):
    """Device-class formats (TiffDevice etc.) must appear in pdf/net formats.json."""

    @classmethod
    def setUpClass(cls):
        cls._tmpdir = tempfile.mkdtemp(prefix="scout_pdfnet_device_test_")
        env = {**os.environ, "PYTHONPATH": str(_REPO_ROOT / "scripts" / "pipeline")}
        result = subprocess.run(
            [
                sys.executable,
                str(_SCOUT_SCRIPT),
                "pdf",
                "net",
                str(_PDF_NET_CACHE),
                cls._tmpdir,
            ],
            capture_output=True,
            text=True,
            env=env,
        )
        cls._scout_returncode = result.returncode
        cls._scout_stderr = result.stderr
        formats_path = Path(cls._tmpdir) / "formats.json"
        if formats_path.exists():
            cls._formats = json.loads(formats_path.read_text(encoding="utf-8"))
        else:
            cls._formats = []
        cls._format_names_lower = {f["format"].lower() for f in cls._formats}
        cls._export_names_lower = {
            f["format"].lower()
            for f in cls._formats
            if f.get("direction") == "export"
        }

    def test_scout_exits_zero(self):
        self.assertEqual(
            self._scout_returncode,
            0,
            f"scout.py exited {self._scout_returncode}:\n{self._scout_stderr}",
        )

    def test_tiff_device_produces_export_entry(self):
        """TiffDevice.cs must produce a TIFF export entry (direction='export')."""
        self.assertIn(
            "tiff",
            self._export_names_lower,
            f"Expected 'Tiff' export entry from TiffDevice.cs but not found.\n"
            f"Export formats found: {sorted(self._export_names_lower)}",
        )

    def test_page_device_not_in_formats(self):
        """PageDevice is abstract — 'page' must NOT appear as a format entry."""
        self.assertNotIn(
            "page",
            self._format_names_lower,
            "'Page' appeared as a format entry — PageDevice abstract base is a false positive.",
        )

    def test_image_device_not_in_formats(self):
        """ImageDevice is an abstract base — 'image' must NOT appear (already in FP list)."""
        self.assertNotIn(
            "image",
            self._format_names_lower,
            "'Image' appeared as a format entry — ImageDevice is a false positive.",
        )

    def test_document_device_not_in_formats(self):
        """DocumentDevice → 'Document' is in false-positive list — must not appear."""
        self.assertNotIn(
            "document",
            self._format_names_lower,
            "'Document' appeared as a format entry — DocumentDevice is a false positive.",
        )
