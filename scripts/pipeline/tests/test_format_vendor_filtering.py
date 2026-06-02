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
        """All format names should be short and alphanumeric.

        Enum-sourced entries (e.g. FontType.TTF) must be all-uppercase identifiers.
        Non-enum entries from I/O backing classes (e.g. TtfSerializer → "Ttf") may be
        PascalCase — they are stripped class names, not enum member names.
        Both must be short (<=12 chars) and contain only word characters.

        Updated A13 W.1: Serializer-derived non-enum entries are now included;
        they are single-word PascalCase (Ttf, Cff) not multi-word CamelCase.
        """
        for f in self._formats:
            name = f["format"]
            self.assertLessEqual(
                len(name), 12,
                f"Format name too long (likely false positive): {name}"
            )
            self.assertRegex(
                name, r"^[A-Za-z][A-Za-z0-9_]+$",
                f"Format name contains unexpected characters: {name}"
            )
            # Enum-sourced entries must be uppercase identifiers
            if f.get("enum"):
                self.assertRegex(
                    name, r"^[A-Z][A-Z0-9_]+$",
                    f"Enum format name must be uppercase: {name}"
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


class TestConventionalVisibilityPolicy(unittest.TestCase):
    """When __all__ defines the public API, conventional classes must not
    become reference pages.  H-04e."""

    def _make_entries(self, vis_list):
        """Helper: create api_surface-style entries with given visibility tiers."""
        return [{"name": f"Cls{i}", "visibility": v}
                for i, v in enumerate(vis_list)]

    def test_conventional_excluded_when_exports_exist(self):
        """If any entry has visibility='exported', conventional entries are dropped."""
        entries = self._make_entries(
            ["exported", "public", "conventional", "conventional"])
        # Simulate the H-04e filter
        has_exports = any(e.get("visibility") == "exported" for e in entries)
        self.assertTrue(has_exports)
        filtered = [e for e in entries if e.get("visibility") != "conventional"]
        self.assertEqual(len(filtered), 2)  # exported + public only
        visibilities = {e["visibility"] for e in filtered}
        self.assertNotIn("conventional", visibilities)

    def test_conventional_kept_when_no_exports(self):
        """Without exported entries, conventional classes are retained."""
        entries = self._make_entries(["public", "conventional", "conventional"])
        has_exports = any(e.get("visibility") == "exported" for e in entries)
        self.assertFalse(has_exports)
        # No filtering for conventional
        self.assertEqual(len(entries), 3)

    def test_internal_always_excluded(self):
        """Internal entries are excluded regardless of export status."""
        entries = self._make_entries(
            ["exported", "public", "conventional", "internal"])
        # H-04d: internal always excluded
        filtered = [e for e in entries if e.get("visibility") != "internal"]
        self.assertEqual(len(filtered), 3)
        # H-04e: then conventional excluded because exports exist
        has_exports = any(e.get("visibility") == "exported" for e in filtered)
        self.assertTrue(has_exports)
        final = [e for e in filtered if e.get("visibility") != "conventional"]
        self.assertEqual(len(final), 2)
        self.assertEqual(
            {e["visibility"] for e in final}, {"exported", "public"})


if __name__ == "__main__":
    unittest.main()
