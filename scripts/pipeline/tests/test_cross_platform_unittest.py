from __future__ import annotations

import json
import tempfile
import unittest
from pathlib import Path

import sys

PIPELINE_DIR = Path(__file__).resolve().parents[1]
if str(PIPELINE_DIR) not in sys.path:
    sys.path.insert(0, str(PIPELINE_DIR))

from cross_platform_audit import compare_family


class CrossPlatformAuditTests(unittest.TestCase):
    def test_detects_format_direction_difference(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp) / "knowledge" / "fake"
            net = root / "net" / "merged"
            python = root / "python" / "merged"
            net.mkdir(parents=True)
            python.mkdir(parents=True)
            (net / "formats.json").write_text(
                json.dumps([{"ext": "fbx", "direction": "import"}]),
                encoding="utf-8",
            )
            (python / "formats.json").write_text(
                json.dumps([{"ext": "fbx", "direction": "export"}]),
                encoding="utf-8",
            )
            report = compare_family("fake", knowledge_root=root.parent)
            self.assertEqual(report["issue_count"], 1)
            self.assertEqual(report["issues"][0]["format"], "fbx")


if __name__ == "__main__":
    unittest.main()
