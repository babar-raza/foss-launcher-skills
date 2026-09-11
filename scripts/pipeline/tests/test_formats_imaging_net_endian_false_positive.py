"""Regression test: ImageFormat's real 11 formats must be extracted, and
EndianReader must not produce a false-positive "Endian" format entry, when
running the format extractor against the imaging/net clone cache.

Root cause (found live 2026-09-11, bootstrapping imaging/net knowledge --
reports/skill-gaps/2026-09-11-imaging-net-pipeline-hardening-prerequisites.md):

  ImageFormat (a plain enum literally named "{Domain}Format", e.g.
  Aspose.Imaging.Foss.ImageFormat) was never recognized as a format-defining
  enum at all: detect_formats()'s format_pattern only matched a fixed list
  of specific suffixes (FileFormat, SaveFormat, ExportFormat, LoadFormat,
  ImportFormat, OutputFormat, InputFormat, SourceFormat, FormatType,
  SupportedFormat, FileType, FontType) -- "ImageFormat" matches none of
  them. Confirmed: this repo's formats.json ended up with exactly 1 entry,
  "Endian" (direction unset), sourced from EndianReader.cs matching the
  unrelated importer_pattern's "Reader" suffix -- while the enum-extraction
  code path that would have correctly emitted all 11 real formats (with
  enum_direction="detect", since a plain-named format enum with no
  Save/Export/Load/Import qualifier correctly infers detect-only capability,
  matching this library's real, narrow, probe-only scope) never ran because
  format_pattern never matched the enum's name in the first place.

  Fix: format_pattern gained a general `\\w+Format$` alternative (an enum
  name ending in the literal word "Format", suffix-anchored) so a plain
  "{Domain}Format" enum is recognized portfolio-wide, not just for imaging/
  net -- alongside adding "endian" to _FALSE_POSITIVE_NAMES as a
  belt-and-suspenders suppression of the specific false positive already
  observed live.

This test runs scout.py end-to-end against the imaging/net clone cache and
verifies: (a) "endian" does not appear in formats.json output; (b) the real
format names (a representative subset: png, jpeg, dicom) DO appear, each
with direction="detect" (never "import"/"export" -- this library never
decodes/edits/converts, only detects, per its own README and this mission's
scope-boundary requirement)."""
import json
import os
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

_REPO_ROOT = Path(__file__).resolve().parent.parent.parent.parent
_IMAGING_NET_CACHE = _REPO_ROOT / "runs" / ".clone_cache" / "aspose_imaging_net"
_IMAGING_NET_HAS_SOURCES = (
    bool(list(_IMAGING_NET_CACHE.rglob("*.cs"))[:1])
    if _IMAGING_NET_CACHE.exists()
    else False
)
_SCOUT_SCRIPT = _REPO_ROOT / "scripts" / "pipeline" / "commands" / "knowledge" / "scout.py"


@unittest.skipUnless(
    _IMAGING_NET_HAS_SOURCES,
    "Clone cache absent or empty — run /repo-scout imaging net first",
)
class TestImagingNetFormatExtraction(unittest.TestCase):
    """ImageFormat's real formats must be extracted; EndianReader must not
    emit a false-positive "Endian" format entry."""

    @classmethod
    def setUpClass(cls):
        cls._tmpdir = tempfile.mkdtemp(prefix="scout_imaging_net_fmt_test_")
        env = {**os.environ, "PYTHONPATH": str(_REPO_ROOT / "scripts" / "pipeline")}
        result = subprocess.run(
            [
                sys.executable,
                str(_SCOUT_SCRIPT),
                "imaging",
                "net",
                str(_IMAGING_NET_CACHE),
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

    def test_endian_false_positive_absent(self):
        self.assertNotIn(
            "endian", self._by_name,
            f"'Endian' false-positive format entry still present: {self._formats}",
        )

    def test_real_formats_present_with_detect_direction(self):
        for expected in ("png", "jpeg", "dicom"):
            self.assertIn(
                expected, self._by_name,
                f"expected real format {expected!r} missing from formats.json: {self._formats}",
            )
            self.assertEqual(
                self._by_name[expected]["direction"], "detect",
                f"{expected} should be direction=detect (probe-only library, "
                f"never decode/edit/convert) — got {self._by_name[expected]!r}",
            )

    def test_at_least_eleven_real_formats_extracted(self):
        """The README documents 11 supported formats (PNG, JPEG, GIF, BMP,
        WebP, ICO, TIFF, PSD, EMF, WMF, DICOM) -- ImageFormat's enum has 12
        members including Unknown, so at least 11 non-Unknown entries are
        expected once the enum is correctly recognized."""
        real = [f for f in self._formats if f["format"].lower() not in ("unknown", "endian")]
        self.assertGreaterEqual(
            len(real), 11,
            f"expected >=11 real format entries, got {len(real)}: {self._formats}",
        )
