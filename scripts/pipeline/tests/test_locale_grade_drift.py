"""Unit tests for locale_grade_drift.py — dir-separated KB locale detection.

Tests that:
- _get_locale_codes() discovers locale dirs (ar, fr) in a mock KB root
- _iter_dir_separated_pairs() yields correct (en_file, locale_file, locale_code) pairs
- check_dir_separated_locales() detects GRADE_FLOOR_VIOLATION and LOCALE_DRIFT
- Existing co-located scan (check_directory) is unaffected by the new code

Root cause guarded (LOCALE-KB-GRADE-001 / A13 W.2):
  locale_grade_drift.py previously only detected co-located locale files
  (index.md + index.ar.md in the same directory). KB pages use a
  directory-separated convention: en/{path} / ar/{path}. This test suite
  verifies the fix detects both conventions.
"""
from __future__ import annotations

import sys
import tempfile
import unittest
from pathlib import Path

_PIPELINE_ROOT = Path(__file__).resolve().parent.parent
if str(_PIPELINE_ROOT) not in sys.path:
    sys.path.insert(0, str(_PIPELINE_ROOT))

# The script lives in commands/diagnostics/ — add its parent too
_DIAG_DIR = (
    _PIPELINE_ROOT / "commands" / "diagnostics"
)
if str(_DIAG_DIR) not in sys.path:
    sys.path.insert(0, str(_DIAG_DIR))

from locale_grade_drift import (  # noqa: E402
    _get_locale_codes,
    _iter_dir_separated_pairs,
    check_dir_separated_locales,
    check_directory,
)


def _write(path: Path, content: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(content, encoding="utf-8")


class TestGetLocaleCodes(unittest.TestCase):
    """Tests for _get_locale_codes()."""

    def setUp(self):
        self._tmpdir = Path(tempfile.mkdtemp(prefix="lgd_test_"))

    def test_discovers_locale_dirs(self):
        """ar/ and fr/ dirs with .md files are returned; en/ is excluded."""
        root = self._tmpdir
        _write(root / "en" / "page.md", "---\ngrade: B\n---\n")
        _write(root / "ar" / "page.md", "---\ngrade: C\n---\n")
        _write(root / "fr" / "page.md", "---\ngrade: B\n---\n")
        codes = _get_locale_codes(root)
        self.assertIn("ar", codes)
        self.assertIn("fr", codes)
        self.assertNotIn("en", codes)

    def test_excludes_dirs_without_md_files(self):
        """Empty locale dirs (no .md files) are not returned."""
        root = self._tmpdir
        _write(root / "en" / "page.md", "---\ngrade: B\n---\n")
        (root / "de").mkdir(parents=True, exist_ok=True)  # no .md files
        codes = _get_locale_codes(root)
        self.assertNotIn("de", codes)

    def test_empty_root_returns_empty_list(self):
        root = self._tmpdir / "nonexistent"
        codes = _get_locale_codes(root)
        self.assertEqual(codes, [])


class TestIterDirSeparatedPairs(unittest.TestCase):
    """Tests for _iter_dir_separated_pairs()."""

    def setUp(self):
        self._tmpdir = Path(tempfile.mkdtemp(prefix="lgd_test_"))

    def test_yields_matching_pairs(self):
        """Yields (en_file, locale_file, locale_code) when both files exist."""
        root = self._tmpdir
        _write(root / "en" / "email" / "net" / "how-to.md", "---\ngrade: B\n---\n")
        _write(root / "ar" / "email" / "net" / "how-to.md", "---\ngrade: C\n---\n")

        pairs = list(_iter_dir_separated_pairs(root, ["ar"]))
        self.assertEqual(len(pairs), 1)
        en_f, loc_f, code = pairs[0]
        self.assertEqual(code, "ar")
        self.assertTrue(str(en_f).endswith("how-to.md"))
        self.assertIn("ar", str(loc_f))

    def test_no_pair_when_locale_file_absent(self):
        """No pair yielded if locale file does not exist."""
        root = self._tmpdir
        _write(root / "en" / "email" / "page.md", "---\ngrade: B\n---\n")
        # ar/ directory exists but not this specific page
        (root / "ar").mkdir(parents=True, exist_ok=True)

        pairs = list(_iter_dir_separated_pairs(root, ["ar"]))
        self.assertEqual(len(pairs), 0)

    def test_en_subpath_filter(self):
        """en_sub restricts scan to a subpath of en/."""
        root = self._tmpdir
        _write(root / "en" / "email" / "page.md", "---\ngrade: B\n---\n")
        _write(root / "en" / "cells" / "page.md", "---\ngrade: B\n---\n")
        _write(root / "ar" / "email" / "page.md", "---\ngrade: C\n---\n")
        _write(root / "ar" / "cells" / "page.md", "---\ngrade: C\n---\n")

        # Restrict to email only
        en_sub = root / "en" / "email"
        pairs = list(_iter_dir_separated_pairs(root, ["ar"], en_sub=en_sub))
        paths = [str(en_f) for en_f, _, _ in pairs]
        self.assertTrue(all("email" in p for p in paths), f"Expected only email: {paths}")
        self.assertFalse(any("cells" in p for p in paths), f"cells leaked: {paths}")


class TestCheckDirSeparatedLocales(unittest.TestCase):
    """Tests for check_dir_separated_locales() — floor violations and drift."""

    def setUp(self):
        self._tmpdir = Path(tempfile.mkdtemp(prefix="lgd_test_"))

    def test_detects_grade_floor_violation(self):
        """A locale page with grade C (below B floor) is reported."""
        root = self._tmpdir
        _write(root / "en" / "kb" / "page.md", "---\ngrade: B\n---\n")
        _write(root / "ar" / "kb" / "page.md", "---\ngrade: C\n---\n")

        findings = check_dir_separated_locales(root, _repo_root=root)
        floor_viols = [f for f in findings if f["type"] == "GRADE_FLOOR_VIOLATION"]
        self.assertTrue(len(floor_viols) >= 1, "Expected at least one GRADE_FLOOR_VIOLATION")
        viol = floor_viols[0]
        self.assertEqual(viol["locale_grade"], "C")
        self.assertEqual(viol["locale_code"], "ar")
        self.assertEqual(viol["convention"], "dir_separated")

    def test_detects_locale_drift(self):
        """Locale page with grade B when EN is A is reported as LOCALE_DRIFT."""
        root = self._tmpdir
        _write(root / "en" / "kb" / "page.md", "---\ngrade: A\n---\n")
        _write(root / "ar" / "kb" / "page.md", "---\ngrade: B\n---\n")

        findings = check_dir_separated_locales(root, _repo_root=root)
        drifts = [f for f in findings if f["type"] == "LOCALE_DRIFT"]
        self.assertTrue(len(drifts) >= 1, "Expected at least one LOCALE_DRIFT")

    def test_draft_pages_exempt(self):
        """Locale pages with draft: true are not reported."""
        root = self._tmpdir
        _write(root / "en" / "kb" / "page.md", "---\ngrade: B\n---\n")
        _write(root / "ar" / "kb" / "page.md", "---\ndraft: true\ngrade: C\n---\n")

        findings = check_dir_separated_locales(root, _repo_root=root)
        self.assertEqual(len(findings), 0, "Draft locale page must not trigger findings")

    def test_no_findings_when_no_locale_dirs(self):
        """No findings when there are no locale directories."""
        root = self._tmpdir
        _write(root / "en" / "kb" / "page.md", "---\ngrade: B\n---\n")

        findings = check_dir_separated_locales(root, _repo_root=root)
        self.assertEqual(len(findings), 0)

    def test_family_filter_restricts_scan(self):
        """family_filter restricts detection to the specified family."""
        root = self._tmpdir
        _write(root / "en" / "email" / "net" / "page.md", "---\ngrade: B\n---\n")
        _write(root / "en" / "cells" / "net" / "page.md", "---\ngrade: B\n---\n")
        _write(root / "ar" / "email" / "net" / "page.md", "---\ngrade: C\n---\n")
        _write(root / "ar" / "cells" / "net" / "page.md", "---\ngrade: C\n---\n")

        findings = check_dir_separated_locales(root, family_filter="email", _repo_root=root)
        paths = [f["file"] for f in findings]
        self.assertTrue(all("email" in p for p in paths), f"Only email expected: {paths}")
        self.assertFalse(any("cells" in p for p in paths), f"cells leaked: {paths}")


class TestCheckDirectoryColocated(unittest.TestCase):
    """Existing co-located scan still works (regression guard)."""

    def setUp(self):
        self._tmpdir = Path(tempfile.mkdtemp(prefix="lgd_test_"))

    def test_colocated_floor_violation_still_detected(self):
        """index.md + index.ar.md co-located floor violation detected."""
        subdir = self._tmpdir
        _write(subdir / "page" / "index.md", "---\ngrade: B\n---\n")
        _write(subdir / "page" / "index.ar.md", "---\ngrade: C\n---\n")

        findings = check_directory(subdir, _repo_root=subdir)
        floor_viols = [f for f in findings if f["type"] == "GRADE_FLOOR_VIOLATION"]
        self.assertTrue(len(floor_viols) >= 1, "Co-located floor violation not detected")


if __name__ == "__main__":
    unittest.main()
