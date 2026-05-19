"""Regression test: vendor/private directory filtering in format extraction.

Root cause guarded (CV2-001):
  The format extractor scanned all source files including transpiled vendor
  code (e.g. _brotli/vendor/brotlihaxe.py) and private I/O helpers
  (e.g. _io.py), producing false-positive format names like "Font", "Binary",
  "Bit", "Slice" instead of real formats like TTF, OTF, CFF, WOFF.

Fix: _filter_vendor_paths() in extraction/formats.py skips _-prefixed
directories (except _internal) and vendor/ directories.

This test verifies:
1. font/python produces only real font formats (from FontType enum)
2. No false positives from vendor/private directories
3. _internal/ directories are NOT filtered (slides/python needs them)
"""
import json
import os
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

_REPO_ROOT = Path(__file__).resolve().parent.parent.parent.parent
_SCOUT_SCRIPT = _REPO_ROOT / "scripts" / "pipeline" / "commands" / "knowledge" / "scout.py"

# font/python clone cache
_FONT_CACHE = _REPO_ROOT / "runs" / ".clone_cache" / "aspose_font_python"
_FONT_HAS_SOURCES = bool(list(_FONT_CACHE.rglob("*.py"))[:1]) if _FONT_CACHE.exists() else False

# Expected font format names from FontType enum
_EXPECTED_FONT_FORMATS = {"TTF", "OTF", "CFF", "TYPE1", "TYPE1_PFA", "WOFF", "WOFF2", "EOT"}

# Known false positives that must NOT appear
_FONT_FALSE_POSITIVES = {"Font", "Binary", "Bit", "Slice", "pos", "format", "png",
                         "presentation", "decode_Bit", "decode_bit__BrotliBit"}


@unittest.skipUnless(_FONT_HAS_SOURCES, "Clone cache absent — run repo-scout first")
class TestFontPythonFormatExtraction(unittest.TestCase):
    """End-to-end: font/python must produce real font formats, not vendor noise."""

    @classmethod
    def setUpClass(cls):
        cls._tmpdir = tempfile.mkdtemp(prefix="scout_font_test_")
        env = {**os.environ, "PYTHONPATH": str(_REPO_ROOT / "scripts" / "pipeline")}
        result = subprocess.run(
            [sys.executable, str(_SCOUT_SCRIPT),
             "font", "python",
             str(_FONT_CACHE),
             cls._tmpdir],
            capture_output=True,
            text=True,
            env=env,
        )
        cls._scout_returncode = result.returncode
        cls._scout_stderr = result.stderr
        formats_path = Path(cls._tmpdir) / "formats.json"
        if formats_path.exists():
            cls._formats = json.loads(formats_path.read_text())
        else:
            cls._formats = []

    def test_scout_exits_zero(self):
        self.assertEqual(
            self._scout_returncode, 0,
            f"scout.py exited {self._scout_returncode}:\n{self._scout_stderr}",
        )

    def test_contains_all_expected_formats(self):
        """All FontType enum members must appear in formats.json."""
        found = {f["format"] for f in self._formats}
        missing = _EXPECTED_FONT_FORMATS - found
        self.assertFalse(
            missing,
            f"Missing expected font formats: {missing}\n"
            f"Found: {sorted(found)}"
        )

    def test_no_vendor_false_positives(self):
        """No false-positive format names from vendor/private code."""
        found = {f["format"] for f in self._formats}
        leaked = found & _FONT_FALSE_POSITIVES
        self.assertFalse(
            leaked,
            f"Vendor false positives leaked through: {leaked}\n"
            f"All found: {sorted(found)}\n"
            f"Fix: check _filter_vendor_paths() and _FALSE_POSITIVE_NAMES"
        )

    def test_no_entries_from_brotli_dir(self):
        """No format entries should have file paths containing _brotli/."""
        brotli_entries = [f for f in self._formats if "_brotli/" in f.get("file", "")]
        self.assertEqual(
            len(brotli_entries), 0,
            f"Found {len(brotli_entries)} entries from _brotli/ dir:\n"
            + "\n".join(f"  {e['format']} ({e['file']})" for e in brotli_entries)
        )

    def test_format_names_are_plausible(self):
        """All format names should be short, alphanumeric, uppercase identifiers."""
        for f in self._formats:
            name = f["format"]
            self.assertLessEqual(
                len(name), 12,
                f"Format name too long (likely false positive): {name}"
            )
            self.assertRegex(
                name, r"^[A-Z][A-Z0-9_]+$",
                f"Format name doesn't match expected pattern: {name}"
            )


class TestFilterVendorPaths(unittest.TestCase):
    """Unit tests for _filter_vendor_paths()."""

    def test_filters_underscore_prefixed_dirs(self):
        from extraction.formats import _filter_vendor_paths
        pkg = Path("/pkg")
        files = [
            pkg / "module.py",
            pkg / "_brotli" / "encode.py",
            pkg / "_brotli" / "vendor" / "lib.py",
            pkg / "_io.py",  # file, not dir — should pass
        ]
        result = _filter_vendor_paths(files, pkg)
        names = [str(f.relative_to(pkg)) for f in result]
        self.assertIn("module.py", names)
        self.assertIn("_io.py", names)
        self.assertNotIn("_brotli/encode.py", [n.replace("\\", "/") for n in names])
        self.assertNotIn("_brotli/vendor/lib.py", [n.replace("\\", "/") for n in names])

    def test_exempts_internal_dir(self):
        from extraction.formats import _filter_vendor_paths
        pkg = Path("/pkg")
        files = [
            pkg / "_internal" / "export" / "pptx_exporter.py",
            pkg / "_internal" / "opc" / "reader.py",
        ]
        result = _filter_vendor_paths(files, pkg)
        self.assertEqual(len(result), 2, "_internal/ files should NOT be filtered")

    def test_filters_vendor_dir(self):
        from extraction.formats import _filter_vendor_paths
        pkg = Path("/pkg")
        files = [
            pkg / "vendor" / "lib.py",
            pkg / "third_party" / "util.py",
        ]
        result = _filter_vendor_paths(files, pkg)
        self.assertEqual(len(result), 0, "vendor/ and third_party/ should be filtered")


if __name__ == "__main__":
    unittest.main()
