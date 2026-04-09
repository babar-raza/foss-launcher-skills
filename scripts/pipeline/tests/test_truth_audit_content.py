"""Tests for truth_audit_content.py (S-85)."""
from __future__ import annotations

import json
import sys
import tempfile
import unittest
from pathlib import Path
from unittest.mock import MagicMock, patch

PIPELINE_DIR = Path(__file__).resolve().parent.parent
if str(PIPELINE_DIR) not in sys.path:
    sys.path.insert(0, str(PIPELINE_DIR))

import truth_audit_content as tac  # noqa: E402


class TestUnitIds(unittest.TestCase):
    """Unit ID generation must be stable and path-based."""

    def test_make_unit_id_format(self):
        uid = tac.make_unit_id("words", "python", "content/docs/page.md", 42, "P")
        self.assertTrue(uid.startswith("U-words-python-"))
        self.assertIn("-L42-P", uid)

    def test_unit_id_stability(self):
        """Same inputs produce the same ID."""
        a = tac.make_unit_id("words", "python", "content/docs/page.md", 10, "H")
        b = tac.make_unit_id("words", "python", "content/docs/page.md", 10, "H")
        self.assertEqual(a, b)

    def test_unit_id_differs_by_line(self):
        a = tac.make_unit_id("words", "python", "content/docs/page.md", 10, "P")
        b = tac.make_unit_id("words", "python", "content/docs/page.md", 20, "P")
        self.assertNotEqual(a, b)

    def test_unit_id_differs_by_type(self):
        a = tac.make_unit_id("words", "python", "content/docs/page.md", 10, "P")
        b = tac.make_unit_id("words", "python", "content/docs/page.md", 10, "C")
        self.assertNotEqual(a, b)


class TestFindingIds(unittest.TestCase):
    """Finding IDs must be stable and type-coded."""

    def test_finding_id_format(self):
        fid = tac.make_finding_id("words", "python", "unsupported-claim",
                                  "content/docs/page.md", 42, "some text")
        self.assertTrue(fid.startswith("F-words-python-uclm-"))

    def test_finding_id_stability(self):
        a = tac.make_finding_id("words", "python", "fabricated-claim",
                                "page.md", 10, "claim text")
        b = tac.make_finding_id("words", "python", "fabricated-claim",
                                "page.md", 10, "claim text")
        self.assertEqual(a, b)


class TestDecomposition(unittest.TestCase):
    """Content decomposition into reviewable units."""

    def _write_page(self, tmpdir: Path, content: str) -> Path:
        filepath = tmpdir / "content" / "docs.aspose.org" / "en" / "words" / "python" / "test.md"
        filepath.parent.mkdir(parents=True, exist_ok=True)
        filepath.write_text(content, encoding="utf-8")
        return filepath

    def test_heading_extraction(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            tmpdir = Path(tmpdir)
            with patch.object(tac, '_REPO_ROOT', tmpdir):
                fp = self._write_page(tmpdir, "---\ntitle: Test\n---\n## My Heading\n\nSome text here.\n")
                units = tac.decompose_page(fp, "words", "python")
                headings = [u for u in units if u["type"] == "heading"]
                self.assertEqual(len(headings), 1)
                self.assertEqual(headings[0]["text"], "My Heading")

    def test_code_block_extraction(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            tmpdir = Path(tmpdir)
            with patch.object(tac, '_REPO_ROOT', tmpdir):
                content = "---\ntitle: Test\n---\n\n```python\nfrom aspose import words\n```\n"
                fp = self._write_page(tmpdir, content)
                units = tac.decompose_page(fp, "words", "python")
                code_blocks = [u for u in units if u["type"] == "code_block"]
                self.assertEqual(len(code_blocks), 1)
                self.assertIn("from aspose import words", code_blocks[0]["text"])

    def test_table_row_extraction(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            tmpdir = Path(tmpdir)
            with patch.object(tac, '_REPO_ROOT', tmpdir):
                content = "---\ntitle: Test\n---\n\n| Method | Return |\n|--------|--------|\n| save() | None |\n"
                fp = self._write_page(tmpdir, content)
                units = tac.decompose_page(fp, "words", "python")
                rows = [u for u in units if u["type"] == "table_row"]
                # Header row + data row (separator skipped)
                self.assertGreaterEqual(len(rows), 1)

    def test_list_item_extraction(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            tmpdir = Path(tmpdir)
            with patch.object(tac, '_REPO_ROOT', tmpdir):
                content = "---\ntitle: Test\n---\n\n- Supports DOCX format\n- Supports PDF format\n"
                fp = self._write_page(tmpdir, content)
                units = tac.decompose_page(fp, "words", "python")
                items = [u for u in units if u["type"] == "list_item"]
                self.assertEqual(len(items), 2)

    def test_paragraph_extraction(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            tmpdir = Path(tmpdir)
            with patch.object(tac, '_REPO_ROOT', tmpdir):
                content = "---\ntitle: Test\n---\n\nThe Document class provides methods for loading and saving files.\n\nAnother paragraph with more information about formats.\n"
                fp = self._write_page(tmpdir, content)
                units = tac.decompose_page(fp, "words", "python")
                paras = [u for u in units if u["type"] == "paragraph"]
                self.assertGreaterEqual(len(paras), 1)

    def test_frontmatter_skipped(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            tmpdir = Path(tmpdir)
            with patch.object(tac, '_REPO_ROOT', tmpdir):
                content = "---\ntitle: Secret Field\ndescription: Not a unit\n---\n\nReal content here for testing.\n"
                fp = self._write_page(tmpdir, content)
                units = tac.decompose_page(fp, "words", "python")
                # No unit should contain frontmatter content
                for u in units:
                    self.assertNotIn("Secret Field", u["text"])

    def test_unit_type_filter(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            tmpdir = Path(tmpdir)
            with patch.object(tac, '_REPO_ROOT', tmpdir):
                content = "---\ntitle: Test\n---\n## Heading\n\nParagraph text that is long enough.\n"
                fp = self._write_page(tmpdir, content)
                units = tac.decompose_page(fp, "words", "python", unit_types={"H"})
                types = {u["type"] for u in units}
                self.assertEqual(types, {"heading"})


class TestVerifyUnit(unittest.TestCase):
    """Per-unit truth verification."""

    def _make_knowledge(self):
        k = MagicMock()
        k.available = True
        k.classes = {"Document": {}, "SaveFormat": {}}
        k.methods = {"Document": {"save", "get_text"}}
        k.properties = {"Document": {"text", "range"}}
        k.enum_members = {"SaveFormat": {"PDF", "DOCX", "MARKDOWN"}}
        k.has_method = lambda c, m: m in k.methods.get(c, set())
        k.has_property = lambda c, p: p in k.properties.get(c, set())
        k.repo_sha = "abc123"
        k.version = "1.0.0"
        return k

    def test_verified_with_api_and_claim_overlap(self):
        knowledge = self._make_knowledge()
        claims = [{"id": "CLM-001", "text": "Document class provides save method for saving files"}]
        claim_index = [("CLM-001", claims[0]["text"], tac._tokenize(claims[0]["text"]))]
        unit = {
            "id": "U-test",
            "file": "test.md",
            "line_start": 10,
            "line_end": 10,
            "type": "paragraph",
            "text": "The `Document.save` method saves files to the specified path.",
        }
        result = tac.verify_unit(unit, knowledge, claims, [], {}, None, claim_index)
        self.assertEqual(result["verdict"], tac.VERDICT_VERIFIED)
        self.assertIsNone(result["defect_origin"])

    def test_fabricated_api(self):
        knowledge = self._make_knowledge()
        unit = {
            "id": "U-test",
            "file": "test.md",
            "line_start": 20,
            "line_end": 20,
            "type": "paragraph",
            "text": "Call `Document.nonexistent_method` to perform the operation.",
        }
        result = tac.verify_unit(unit, knowledge, [], [], {}, None, [])
        self.assertEqual(result["verdict"], tac.VERDICT_FABRICATED)
        self.assertEqual(result["defect_origin"], tac.ORIGIN_GENERATION_FABRICATION)

    def test_forbidden_claim_detected(self):
        knowledge = self._make_knowledge()
        forbidden = ["Document supports FBX export natively"]
        unit = {
            "id": "U-test",
            "file": "test.md",
            "line_start": 30,
            "line_end": 30,
            "type": "paragraph",
            "text": "The Document class supports FBX export natively for all formats.",
        }
        result = tac.verify_unit(unit, knowledge, [], forbidden, {}, None, [])
        self.assertEqual(result["verdict"], tac.VERDICT_CONTRADICTED)

    def test_structural_prose_unverifiable(self):
        knowledge = self._make_knowledge()
        unit = {
            "id": "U-test",
            "file": "test.md",
            "line_start": 40,
            "line_end": 40,
            "type": "paragraph",
            "text": "In this section, we will explore the key features of the library.",
        }
        result = tac.verify_unit(unit, knowledge, [], [], {}, None, [])
        self.assertEqual(result["verdict"], tac.VERDICT_UNVERIFIABLE)

    def test_short_unit_unverifiable(self):
        knowledge = self._make_knowledge()
        unit = {
            "id": "U-test",
            "file": "test.md",
            "line_start": 50,
            "line_end": 50,
            "type": "paragraph",
            "text": "OK",
        }
        result = tac.verify_unit(unit, knowledge, [], [], {}, None, [])
        self.assertEqual(result["verdict"], tac.VERDICT_UNVERIFIABLE)


class TestStateDelta(unittest.TestCase):
    """Delta tracking across runs."""

    def test_new_findings(self):
        prior = []
        new = [{"id": "F-1", "type": "unsupported-claim"}]
        merged, delta = tac.merge_findings(prior, new)
        self.assertEqual(delta["new"], 1)
        self.assertEqual(delta["fixed"], 0)
        self.assertEqual(merged[0]["status"], "open")

    def test_fixed_findings(self):
        prior = [{"id": "F-1", "type": "unsupported-claim", "status": "open"}]
        new = []
        merged, delta = tac.merge_findings(prior, new)
        self.assertEqual(delta["fixed"], 1)
        self.assertEqual(delta["new"], 0)
        fixed = [f for f in merged if f["id"] == "F-1"]
        self.assertEqual(fixed[0]["status"], "fixed")

    def test_regression_findings(self):
        prior = [{"id": "F-1", "type": "unsupported-claim", "status": "fixed"}]
        new = [{"id": "F-1", "type": "unsupported-claim"}]
        merged, delta = tac.merge_findings(prior, new)
        self.assertEqual(delta["regressions"], 1)
        regressed = [f for f in merged if f["id"] == "F-1" and f.get("status") == "regression"]
        self.assertEqual(len(regressed), 1)

    def test_unchanged_findings(self):
        prior = [{"id": "F-1", "type": "x", "status": "open"}]
        new = [{"id": "F-1", "type": "x"}]
        merged, delta = tac.merge_findings(prior, new)
        self.assertEqual(delta["unchanged"], 1)


class TestStateIO(unittest.TestCase):
    """State file read/write."""

    def test_save_and_load(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            with patch.object(tac, 'STATE_DIR', Path(tmpdir)):
                state = {"family": "words", "platform": "python",
                         "findings": [{"id": "F-1"}]}
                tac.save_state(state, "words", "python")
                loaded = tac.load_state("words", "python")
                self.assertEqual(loaded["family"], "words")
                self.assertEqual(len(loaded["findings"]), 1)

    def test_load_missing_returns_empty(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            with patch.object(tac, 'STATE_DIR', Path(tmpdir)):
                loaded = tac.load_state("words", "python")
                self.assertEqual(loaded["family"], "words")
                self.assertEqual(loaded["findings"], [])


if __name__ == "__main__":
    unittest.main()
