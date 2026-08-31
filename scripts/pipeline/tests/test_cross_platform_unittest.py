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

    def test_same_platform_multiple_entries_aggregate_not_last_write_wins(self):
        """ST-144: a format with separate Importer/Exporter (or Load/Save) entries
        for the SAME platform must aggregate to "both", not silently drop all but
        whichever entry the dict comprehension happened to read last."""
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp) / "knowledge" / "fake"
            net = root / "net" / "merged"
            typescript = root / "typescript" / "merged"
            net.mkdir(parents=True)
            typescript.mkdir(parents=True)
            (net / "formats.json").write_text(
                json.dumps([{"format": "Fbx", "direction": "both"}]),
                encoding="utf-8",
            )
            # Two separate entries for the same format+platform, export listed
            # first, import listed last -- the pre-fix code kept only "import".
            (typescript / "formats.json").write_text(
                json.dumps([
                    {"format": "Fbx", "file": "FbxExporter.ts", "direction": "export"},
                    {"format": "Fbx", "file": "FbxImporter.ts", "direction": "import"},
                ]),
                encoding="utf-8",
            )
            report = compare_family("fake", knowledge_root=root.parent)
            self.assertEqual(report["issue_count"], 0, report["issues"])

    def test_genuine_cross_platform_mismatch_still_detected_after_aggregation(self):
        """Aggregation must not mask a REAL discrepancy: one platform only ever
        exports a format while another genuinely supports both directions."""
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp) / "knowledge" / "fake"
            net = root / "net" / "merged"
            typescript = root / "typescript" / "merged"
            net.mkdir(parents=True)
            typescript.mkdir(parents=True)
            (net / "formats.json").write_text(
                json.dumps([{"format": "Fbx", "direction": "export"}]),
                encoding="utf-8",
            )
            (typescript / "formats.json").write_text(
                json.dumps([
                    {"format": "Fbx", "file": "FbxExporter.ts", "direction": "export"},
                    {"format": "Fbx", "file": "FbxImporter.ts", "direction": "import"},
                ]),
                encoding="utf-8",
            )
            report = compare_family("fake", knowledge_root=root.parent)
            self.assertEqual(report["issue_count"], 1)
            platforms = report["issues"][0]["platforms"]
            self.assertEqual(platforms["net"], "export")
            self.assertEqual(platforms["typescript"], "both")


if __name__ == "__main__":
    unittest.main()
