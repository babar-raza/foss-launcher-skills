"""Regression test: PptxExporter's SaveFormat/SourceFormat members must not be enum_only.

Root cause guarded (TASK-FMT-SRC-02/03):
  _collect_source_files() applied the 500-file cap before deterministic ordering,
  causing pptx_exporter.py (rglob position 520 on Windows NTFS) to be excluded
  from the format scan. The priority-sort fix ensures _internal/ files appear
  at priority 0, well within the cap.

This test uses the live clone cache to run scout.py end-to-end and verifies
that the 7 target format entries have the correct direction and functional=True.

Skipped automatically when the clone cache is absent (CI environments without
the local FOSS source checkout).
"""
import json
import os
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

_REPO_ROOT = Path(__file__).resolve().parent.parent.parent.parent
_CLONE_CACHE = _REPO_ROOT / "runs" / ".clone_cache" / "aspose_slides_python"
_CLONE_CACHE_HAS_SOURCES = bool(list(_CLONE_CACHE.rglob("*.py"))[:1]) if _CLONE_CACHE.exists() else False
_SCOUT_SCRIPT = _REPO_ROOT / "scripts" / "pipeline" / "commands" / "knowledge" / "scout.py"

_TARGETS = [
    ("SaveFormat",  "PPTX",  "export",  True),
    ("SaveFormat",  "PPTM",  "export",  True),
    ("SaveFormat",  "PPSX",  "export",  True),
    ("SaveFormat",  "PPSM",  "export",  True),
    ("SaveFormat",  "POTX",  "export",  True),
    ("SaveFormat",  "POTM",  "export",  True),
    ("SourceFormat","PPTX",  "import",  True),
]


@unittest.skipUnless(_CLONE_CACHE_HAS_SOURCES, "Clone cache absent or empty — run repo-scout first")
class TestSlidesPythonPptxFormatsClassification(unittest.TestCase):
    """End-to-end: scout.py must classify PPTX-family formats as functional I/O."""

    @classmethod
    def setUpClass(cls):
        cls._tmpdir = tempfile.mkdtemp(prefix="scout_test_")
        env = {**os.environ, "PYTHONPATH": str(_REPO_ROOT / "scripts" / "pipeline")}
        result = subprocess.run(
            [sys.executable, str(_SCOUT_SCRIPT),
             "slides", "python",
             str(_CLONE_CACHE),
             cls._tmpdir],
            capture_output=True,
            text=True,
            env=env,
        )
        cls._scout_returncode = result.returncode
        cls._scout_stderr = result.stderr
        formats_path = Path(cls._tmpdir) / "formats.json"
        if formats_path.exists():
            cls._formats = {
                (e.get("enum", ""), e.get("format", "")): e
                for e in json.loads(formats_path.read_text())
            }
        else:
            cls._formats = {}

    def test_scout_exits_zero(self):
        self.assertEqual(
            self._scout_returncode, 0,
            f"scout.py exited {self._scout_returncode}:\n{self._scout_stderr}",
        )

    def test_all_pptx_family_formats_classified_correctly(self):
        """All 7 target entries must be direction=correct and functional=True."""
        failures = []
        for enum, fmt, exp_dir, exp_func in _TARGETS:
            entry = self._formats.get((enum, fmt))
            if entry is None:
                failures.append(f"{enum}.{fmt}: MISSING from formats.json")
                continue
            actual_dir = entry.get("direction")
            actual_func = entry.get("functional")
            if actual_dir != exp_dir or actual_func is not exp_func:
                failures.append(
                    f"{enum}.{fmt}: direction={actual_dir!r} (expected {exp_dir!r}), "
                    f"functional={actual_func!r} (expected {exp_func!r})"
                )
        if failures:
            self.fail(
                "PptxExporter format classification regression:\n"
                + "\n".join(f"  {f}" for f in failures)
                + "\n\nThis likely means _collect_source_files() is excluding "
                "_internal/export/pptx_exporter.py again — check the priority-sort "
                "key in tree_helpers.py:_collect_source_files()."
            )


if __name__ == "__main__":
    unittest.main()
