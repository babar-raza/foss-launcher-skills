from __future__ import annotations

import json
import tempfile
import unittest
from pathlib import Path

import yaml

import sys

PIPELINE_DIR = Path(__file__).resolve().parents[1]
if str(PIPELINE_DIR) not in sys.path:
    sys.path.insert(0, str(PIPELINE_DIR))

from stale_detect import scan_product


class StaleDetectTests(unittest.TestCase):
    def _write_knowledge(self, root: Path, repo_sha: str = "abc123") -> None:
        merged = root / "knowledge" / "fake" / "python" / "merged"
        merged.mkdir(parents=True)
        (merged / "api_surface.json").write_text("[]", encoding="utf-8")
        (merged / "claims.json").write_text(
            json.dumps([{"claim_id": "CLM-1", "text": "Fake.Scene.open()"}]),
            encoding="utf-8",
        )
        (merged / "model.yaml").write_text(
            yaml.safe_dump({"repo_sha": repo_sha, "version": "1.0"}),
            encoding="utf-8",
        )

    def _write_content(self, root: Path, body: str) -> None:
        page = root / "content" / "docs.aspose.org" / "en" / "fake" / "python" / "page.md"
        page.parent.mkdir(parents=True)
        page.write_text(body, encoding="utf-8")

    def test_detects_stale_model_sha(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            self._write_knowledge(root, repo_sha="abc123")
            self._write_content(
                root,
                "---\n"
                "title: Test\n"
                "evidence:\n"
                "  model_sha: old999\n"
                "  claims: [CLM-1]\n"
                "---\n\nBody.\n",
            )
            report = scan_product(
                "fake",
                "python",
                content_root=root / "content",
                knowledge_root=root / "knowledge",
            )
            self.assertEqual(report["stale_pages"], 1)
            self.assertIn("stale_model_sha", report["pages"][0]["issues"])

    def test_detects_orphaned_claims(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            self._write_knowledge(root, repo_sha="abc123")
            self._write_content(
                root,
                "---\n"
                "title: Test\n"
                "evidence:\n"
                "  model_sha: abc123\n"
                "  claims: [CLM-999]\n"
                "---\n\nBody.\n",
            )
            report = scan_product(
                "fake",
                "python",
                content_root=root / "content",
                knowledge_root=root / "knowledge",
            )
            self.assertEqual(report["stale_pages"], 1)
            self.assertIn("orphaned_claims", report["pages"][0]["issues"])


if __name__ == "__main__":
    unittest.main()
