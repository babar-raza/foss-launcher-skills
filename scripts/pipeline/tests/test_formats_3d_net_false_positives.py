"""Regression test: BasicLoadOptions and EntityRenderer must not produce false-positive
format entries when running the format extractor against the 3d/net clone cache.

Root causes guarded (TC-R05 cross-product audit 2026-07-12):

  BasicLoadOptions (H-04e):
    internal class in Aspose.ThreeD.Formats namespace. Pass 1b of the format
    extractor matched the XxxLoadOptions pattern and emitted fmt_name="Basic"
    with direction="import". "Basic" is not a user-facing file format — it is an
    internal generic load-options base class. Fix: added "basic" to
    _FALSE_POSITIVE_NAMES.

  EntityRenderer (H-04e):
    abstract class in Aspose.ThreeD.Render namespace (EntityRenderer.cs).
    The importer_pattern matched via the "Renderer" suffix and emitted
    fmt_name="Entity" with direction="export". Entity is not a file format — it
    is the 3D scene entity/object renderer abstraction. Fix: added "entity" to
    _FALSE_POSITIVE_NAMES.

This test runs scout.py end-to-end against the 3d/net clone cache and verifies
that neither "basic" nor "entity" appear in formats.json output.
"""
import json
import os
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

_REPO_ROOT = Path(__file__).resolve().parent.parent.parent.parent
_3D_NET_CACHE = _REPO_ROOT / "runs" / ".clone_cache" / "aspose_3d_net"
_3D_NET_HAS_SOURCES = (
    bool(list(_3D_NET_CACHE.rglob("*.cs"))[:1])
    if _3D_NET_CACHE.exists()
    else False
)
_SCOUT_SCRIPT = _REPO_ROOT / "scripts" / "pipeline" / "commands" / "knowledge" / "scout.py"


@unittest.skipUnless(
    _3D_NET_HAS_SOURCES,
    "Clone cache absent or empty — run /repo-scout 3d net first",
)
class Test3dNetFormatFalsePositives(unittest.TestCase):
    """BasicLoadOptions and EntityRenderer must not emit false-positive format entries."""

    @classmethod
    def setUpClass(cls):
        cls._tmpdir = tempfile.mkdtemp(prefix="scout_3dnet_fp_test_")
        env = {**os.environ, "PYTHONPATH": str(_REPO_ROOT / "scripts" / "pipeline")}
        result = subprocess.run(
            [
                sys.executable,
                str(_SCOUT_SCRIPT),
                "3d",
                "net",
                str(_3D_NET_CACHE),
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

    def test_scout_exits_zero(self):
        self.assertEqual(
            self._scout_returncode,
            0,
            f"scout.py exited {self._scout_returncode}:\n{self._scout_stderr}",
        )

    def test_basic_load_options_not_in_formats(self):
        """BasicLoadOptions is an internal class — 'basic' must NOT appear as a format."""
        self.assertNotIn(
            "basic",
            self._format_names_lower,
            "'Basic' appeared as a format entry — BasicLoadOptions (internal class) "
            "is a false positive. Check _FALSE_POSITIVE_NAMES in formats.py.",
        )

    def test_entity_renderer_not_in_formats(self):
        """EntityRenderer is an abstract Render/ class — 'entity' must NOT appear as a format."""
        self.assertNotIn(
            "entity",
            self._format_names_lower,
            "'Entity' appeared as a format entry — EntityRenderer (Render/ abstract class) "
            "is a false positive. Check _FALSE_POSITIVE_NAMES in formats.py.",
        )

    def test_real_formats_present(self):
        """Core 3d/net formats (FBX, glTF, OBJ, STL) must still be detected after fix."""
        required = {"fbx", "gltf", "obj", "stl"}
        missing = required - self._format_names_lower
        self.assertFalse(
            missing,
            f"Expected core formats missing after _FALSE_POSITIVE_NAMES update: {missing}\n"
            f"All formats found: {sorted(self._format_names_lower)}",
        )


if __name__ == "__main__":
    unittest.main()
