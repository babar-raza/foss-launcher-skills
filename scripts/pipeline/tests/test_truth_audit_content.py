"""Tests for truth_audit_content.py (S-85)."""
from __future__ import annotations

import json
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path
from unittest.mock import MagicMock, patch

PIPELINE_DIR = Path(__file__).resolve().parent.parent
if str(PIPELINE_DIR) not in sys.path:
    sys.path.insert(0, str(PIPELINE_DIR))

import truth_audit_content as tac  # noqa: E402


class TestWindowsEntrypointReliability(unittest.TestCase):
    """The documented root-level command must not depend on shell encoding."""

    def test_direct_script_help_bootstraps_pipeline_imports(self):
        script = PIPELINE_DIR / "commands" / "diagnostics" / "truth_audit_content.py"
        result = subprocess.run(
            [sys.executable, str(script), "--help"],
            cwd=PIPELINE_DIR.parent.parent,
            capture_output=True,
            text=True,
            encoding="utf-8",
            errors="replace",
            timeout=30,
        )
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertNotIn("ModuleNotFoundError", result.stderr)
        self.assertIn("Line-level content truth audit", result.stdout)

    def test_clone_grep_uses_explicit_utf8_replacement(self):
        completed = subprocess.CompletedProcess(
            args=["git"],
            returncode=0,
            stdout="src/Example.java:7:replacement \ufffd text\n",
            stderr="",
        )
        with patch.object(tac.subprocess, "run", return_value=completed) as run:
            matches = tac._grep_clone_cache(Path.cwd(), "replacement")

        self.assertEqual(matches[0]["excerpt"], "replacement \ufffd text")
        self.assertEqual(run.call_args.kwargs["encoding"], "utf-8")
        self.assertEqual(run.call_args.kwargs["errors"], "replace")

    def test_unsupported_findings_use_findings_exit_code(self):
        ledger = {
            "summary": {
                "total_units": 1,
                "claim_units": 1,
                "verified": 0,
                "unverifiable": 0,
                "unsupported": 1,
                "contradicted": 0,
                "fabricated": 0,
                "claim_verification_rate": 0.0,
                "verification_rate": 0.0,
                "defect_rate": 0.0,
                "confidence_bands": {},
            }
        }
        with patch.object(tac, "run_audit", return_value=ledger):
            self.assertEqual(tac.main(["cells", "java", "--no-llm"]), 2)


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

    def tearDown(self):
        tac.configure()

    def _write_page(self, tmpdir: Path, content: str) -> Path:
        filepath = tmpdir / "content" / "docs.aspose.org" / "en" / "words" / "python" / "test.md"
        filepath.parent.mkdir(parents=True, exist_ok=True)
        filepath.write_text(content, encoding="utf-8")
        return filepath

    def test_heading_extraction(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            tmpdir = Path(tmpdir)
            tac.configure(repo_root=tmpdir)
            fp = self._write_page(tmpdir, "---\ntitle: Test\n---\n## My Heading\n\nSome text here.\n")
            units = tac.decompose_page(fp, "words", "python")
            headings = [u for u in units if u["type"] == "heading"]
            self.assertEqual(len(headings), 1)
            self.assertEqual(headings[0]["text"], "My Heading")

    def test_code_block_extraction(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            tmpdir = Path(tmpdir)
            tac.configure(repo_root=tmpdir)
            content = "---\ntitle: Test\n---\n\n```python\nfrom aspose import words\n```\n"
            fp = self._write_page(tmpdir, content)
            units = tac.decompose_page(fp, "words", "python")
            code_blocks = [u for u in units if u["type"] == "code_block"]
            self.assertEqual(len(code_blocks), 1)
            self.assertIn("from aspose import words", code_blocks[0]["text"])

    def test_table_row_extraction(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            tmpdir = Path(tmpdir)
            tac.configure(repo_root=tmpdir)
            content = "---\ntitle: Test\n---\n\n| Method | Return |\n|--------|--------|\n| save() | None |\n"
            fp = self._write_page(tmpdir, content)
            units = tac.decompose_page(fp, "words", "python")
            rows = [u for u in units if u["type"] == "table_row"]
            # Header row + data row (separator skipped)
            self.assertGreaterEqual(len(rows), 1)

    def test_list_item_extraction(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            tmpdir = Path(tmpdir)
            tac.configure(repo_root=tmpdir)
            content = "---\ntitle: Test\n---\n\n- Supports DOCX format\n- Supports PDF format\n"
            fp = self._write_page(tmpdir, content)
            units = tac.decompose_page(fp, "words", "python")
            items = [u for u in units if u["type"] == "list_item"]
            self.assertEqual(len(items), 2)

    def test_paragraph_extraction(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            tmpdir = Path(tmpdir)
            tac.configure(repo_root=tmpdir)
            content = "---\ntitle: Test\n---\n\nThe Document class provides methods for loading and saving files.\n\nAnother paragraph with more information about formats.\n"
            fp = self._write_page(tmpdir, content)
            units = tac.decompose_page(fp, "words", "python")
            paras = [u for u in units if u["type"] == "paragraph"]
            self.assertGreaterEqual(len(paras), 1)

    def test_frontmatter_skipped(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            tmpdir = Path(tmpdir)
            tac.configure(repo_root=tmpdir)
            content = "---\ntitle: Secret Field\ndescription: Not a unit\n---\n\nReal content here for testing.\n"
            fp = self._write_page(tmpdir, content)
            units = tac.decompose_page(fp, "words", "python")
            # No unit should contain frontmatter content
            for u in units:
                self.assertNotIn("Secret Field", u["text"])

    def test_unit_type_filter(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            tmpdir = Path(tmpdir)
            tac.configure(repo_root=tmpdir)
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


class TestReverseMethodIndex(unittest.TestCase):
    """Change A: Bare method/property resolution via reverse index."""

    def _make_knowledge(self):
        k = MagicMock()
        k.available = True
        k.classes = {"Document": {}, "NumberingParser": {}, "StyleParser": {}}
        k.methods = {
            "Document": {"save", "get_text"},
            "NumberingParser": {"is_ordered_list", "parse"},
            "StyleParser": {"get_style_chain"},
        }
        k.properties = {"Document": {"text", "range"}}
        k.enum_members = {"SaveFormat": {"PDF", "DOCX"}}
        k.has_method = lambda c, m: m in k.methods.get(c, set())
        k.has_property = lambda c, p: p in k.properties.get(c, set())
        k.repo_sha = "abc123"
        k.version = "1.0.0"
        return k

    def test_bare_method_resolved_via_index(self):
        """is_ordered_list() should resolve via reverse index to NumberingParser."""
        knowledge = self._make_knowledge()
        method_index = tac._build_method_index(knowledge)
        claims = [{"id": "CLM-1", "text": "is_ordered_list checks if a list is ordered"}]
        claim_index = [("CLM-1", claims[0]["text"], tac._tokenize(claims[0]["text"]))]
        unit = {
            "id": "U-test", "file": "test.md", "line_start": 10, "line_end": 10,
            "type": "paragraph",
            "text": "Use `is_ordered_list()` to distinguish ordered from unordered lists.",
        }
        result = tac.verify_unit(unit, knowledge, claims, [], {}, None, claim_index, method_index)
        self.assertEqual(result["verdict"], tac.VERDICT_VERIFIED)

    def test_bare_method_no_index_backward_compat(self):
        """Without method_index, bare methods are silently skipped (old behavior)."""
        knowledge = self._make_knowledge()
        unit = {
            "id": "U-test", "file": "test.md", "line_start": 10, "line_end": 10,
            "type": "paragraph",
            "text": "Use `is_ordered_list()` to check list ordering behavior in documents.",
        }
        result = tac.verify_unit(unit, knowledge, [], [], {}, None, [])
        # Without index, bare name is skipped — falls through to overlap/unsupported
        self.assertIn(result["verdict"],
                      [tac.VERDICT_UNVERIFIABLE, tac.VERDICT_UNSUPPORTED])

    def test_fabricated_bare_method_detected(self):
        """A bare method not in any class should be FABRICATED via reverse index."""
        knowledge = self._make_knowledge()
        method_index = tac._build_method_index(knowledge)
        unit = {
            "id": "U-test", "file": "test.md", "line_start": 10, "line_end": 10,
            "type": "paragraph",
            "text": "Call `totally_fake_method()` to perform the nonexistent operation.",
        }
        result = tac.verify_unit(unit, knowledge, [], [], {}, None, [], method_index)
        self.assertEqual(result["verdict"], tac.VERDICT_FABRICATED)
        self.assertEqual(result["defect_origin"], tac.ORIGIN_GENERATION_FABRICATION)

    def test_camelcase_bare_method_resolved_java(self):
        """Java-style camelCase bare method should resolve via reverse index."""
        knowledge = self._make_knowledge()
        # Add a camelCase method to the mock
        knowledge.methods["Document"] = {"save", "get_text", "getText"}
        method_index = tac._build_method_index(knowledge)
        claims = [{"id": "CLM-1", "text": "getText returns the document text content"}]
        claim_index = [("CLM-1", claims[0]["text"], tac._tokenize(claims[0]["text"]))]
        unit = {
            "id": "U-test", "file": "test.md", "line_start": 10, "line_end": 10,
            "type": "paragraph",
            "text": "Call `getText()` to retrieve the full document text content.",
        }
        result = tac.verify_unit(unit, knowledge, claims, [], {}, None,
                                 claim_index, method_index, platform="java")
        self.assertEqual(result["verdict"], tac.VERDICT_VERIFIED)

    def test_camelcase_fabricated_method_detected_java(self):
        """Java-style fabricated camelCase method should be FABRICATED."""
        knowledge = self._make_knowledge()
        method_index = tac._build_method_index(knowledge)
        unit = {
            "id": "U-test", "file": "test.md", "line_start": 10, "line_end": 10,
            "type": "paragraph",
            "text": "Call `getNonexistentValue()` to perform the fake operation.",
        }
        result = tac.verify_unit(unit, knowledge, [], [], {}, None,
                                 [], method_index, platform="java")
        self.assertEqual(result["verdict"], tac.VERDICT_FABRICATED)
        self.assertEqual(result["defect_origin"], tac.ORIGIN_GENERATION_FABRICATION)

    def test_camelcase_ignored_for_python(self):
        """camelCase bare names should NOT trigger on Python platform."""
        knowledge = self._make_knowledge()
        method_index = tac._build_method_index(knowledge)
        unit = {
            "id": "U-test", "file": "test.md", "line_start": 10, "line_end": 10,
            "type": "paragraph",
            "text": "The `getValue()` method retrieves data from the document store.",
        }
        result = tac.verify_unit(unit, knowledge, [], [], {}, None,
                                 [], method_index, platform="python")
        # Should NOT be FABRICATED — camelCase not recognized as method-like for Python
        self.assertNotEqual(result["verdict"], tac.VERDICT_FABRICATED)


class TestIsMethodLike(unittest.TestCase):
    """SR-05: _is_method_like platform-aware method detection."""

    def test_snake_case_all_platforms(self):
        self.assertTrue(tac._is_method_like("get_text", "python"))
        self.assertTrue(tac._is_method_like("get_text", "java"))
        self.assertTrue(tac._is_method_like("get_text", ""))

    def test_camelcase_java(self):
        self.assertTrue(tac._is_method_like("getText", "java"))
        self.assertTrue(tac._is_method_like("getValue", "net"))
        self.assertTrue(tac._is_method_like("setWidth", "typescript"))

    def test_camelcase_not_python(self):
        self.assertFalse(tac._is_method_like("getText", "python"))
        self.assertFalse(tac._is_method_like("getValue", ""))

    def test_java_standard_library_types_are_not_methods(self):
        self.assertFalse(tac._is_method_like("InputStream", "java"))
        self.assertFalse(tac._is_method_like("IndexOutOfBoundsException", "java"))

    def test_single_lowercase_word_false(self):
        self.assertFalse(tac._is_method_like("filepath", "python"))
        self.assertFalse(tac._is_method_like("stream", "java"))
        self.assertFalse(tac._is_method_like("pip", "python"))

    def test_uppercase_word_false(self):
        """All-caps or PascalCase without interior lowercase+uppercase transition."""
        self.assertFalse(tac._is_method_like("PDF", "java"))

    def test_multiword_pascalcase_type_name_also_true(self):
        """Documents an existing, unfixed quirk: _is_method_like() cannot
        distinguish a multi-word PascalCase MEMBER name (e.g. "GetBounds")
        from a multi-word PascalCase TYPE/INTERFACE name (e.g. "RectangleF",
        "IFieldWithCalendar") -- both have an interior lowercase-to-uppercase
        transition. This is why _build_type_and_interface_names() must be
        checked BEFORE falling back to this heuristic in verify_unit() --
        see TestBuildTypeAndInterfaceNames and the FABRICATED regression
        tests below."""
        self.assertTrue(tac._is_method_like("RectangleF", "net"))
        self.assertTrue(tac._is_method_like("IFieldWithCalendar", "net"))


class TestBuildTypeAndInterfaceNames(unittest.TestCase):
    """Root cause (found 2026-07-23 via words/net Stage 8 verification):
    interfaces (only ever appear in another class's `bases`) and BCL/
    framework property or return types (e.g. .NET's `RectangleF`) have no
    class entry of their own in api_surface.json, so a bare backtick
    reference to one falls to _is_method_like()'s reverse method/property
    index lookup -- where a TYPE name is correctly never found, producing a
    false FABRICATED verdict on completely accurate content. Confirmed live:
    GroupShape/Shape/ShapeBase's real `Bounds: RectangleF` property, and
    FieldDate/FieldCreateDate/FieldPrintDate/FieldSaveDate's real
    `IFieldWithCalendar` implemented interface, were both reported
    FABRICATED despite being verbatim-correct per api_surface.json.
    """

    def _make_knowledge(self):
        k = MagicMock()
        k.parents = {
            "FieldDate": ["Field", "IFieldCodeTokenInfoProvider", "IFieldWithCalendar"],
            "GroupShape": ["ShapeBase"],
        }
        k.property_types = {("GroupShape", "Bounds"): "RectangleF"}
        k.return_types = {("Document", "ToString"): "string"}
        return k

    def test_interface_from_bases_included(self):
        names = tac._build_type_and_interface_names(self._make_knowledge())
        self.assertIn("IFieldWithCalendar", names)

    def test_base_class_from_bases_included(self):
        names = tac._build_type_and_interface_names(self._make_knowledge())
        self.assertIn("ShapeBase", names)

    def test_property_type_included(self):
        names = tac._build_type_and_interface_names(self._make_knowledge())
        self.assertIn("RectangleF", names)

    def test_return_type_included(self):
        names = tac._build_type_and_interface_names(self._make_knowledge())
        self.assertIn("string", names)

    def test_unrelated_name_not_included(self):
        names = tac._build_type_and_interface_names(self._make_knowledge())
        self.assertNotIn("TotallyMadeUpTypeName", names)

    def test_missing_attributes_handled_gracefully(self):
        """A MagicMock or real Knowledge without these attributes must not
        raise -- getattr(..., {}) defaults must actually be honored."""
        k = MagicMock(spec=[])  # no attributes at all
        names = tac._build_type_and_interface_names(k)
        self.assertEqual(names, set())


class TestVerifyUnitTypeInterfaceRegression(unittest.TestCase):
    """End-to-end regression: verify_unit() must not report FABRICATED for a
    bare type/interface reference that's a real `bases` entry or property
    type, reproducing the exact words/net GroupShape.md and
    date-and-time.md findings."""

    def _make_knowledge(self):
        k = MagicMock()
        k.available = True
        k.classes = {"GroupShape": {}, "FieldDate": {}}
        k.methods = {}
        k.properties = {}
        k.enum_members = {}
        k.has_method = lambda c, m: False
        k.has_property = lambda c, m: False
        k.parents = {
            "FieldDate": ["Field", "IFieldWithCalendar"],
        }
        k.property_types = {("GroupShape", "Bounds"): "RectangleF"}
        k.return_types = {}
        k.repo_sha = "abc123"
        k.version = "1.0.0"
        return k

    def test_property_type_reference_not_fabricated(self):
        knowledge = self._make_knowledge()
        type_names = tac._build_type_and_interface_names(knowledge)
        unit = {
            "id": "U-test",
            "file": "GroupShape.md",
            "line_start": 126,
            "line_end": 126,
            "type": "table_row",
            "text": "| `Bounds` | `RectangleF` | Read/Write | Gets or sets the location and size of the containing block of the shape. |",
        }
        result = tac.verify_unit(
            unit, knowledge, [], [], {}, None, [],
            method_index={}, platform="net", type_names=type_names,
        )
        self.assertNotEqual(result["verdict"], tac.VERDICT_FABRICATED)

    def test_implemented_interface_reference_not_fabricated(self):
        knowledge = self._make_knowledge()
        type_names = tac._build_type_and_interface_names(knowledge)
        unit = {
            "id": "U-test",
            "file": "date-and-time.md",
            "line_start": 179,
            "line_end": 179,
            "type": "table_row",
            "text": "| `IFieldWithCalendar` | Interface implemented by all four classes for calendar-aware field results |",
        }
        result = tac.verify_unit(
            unit, knowledge, [], [], {}, None, [],
            method_index={}, platform="net", type_names=type_names,
        )
        self.assertNotEqual(result["verdict"], tac.VERDICT_FABRICATED)

    def test_genuinely_fabricated_type_still_flagged(self):
        """The fix must not weaken detection of a genuinely invented type
        name -- one that appears in no class's bases and no property/return
        type anywhere in the model. A non-empty method_index is required
        here (an empty dict is falsy in verify_unit's own truthiness check,
        which would silently skip the reverse-lookup fallback regardless of
        this fix and produce a weaker UNSUPPORTED verdict instead -- not
        what this test is isolating)."""
        knowledge = self._make_knowledge()
        type_names = tac._build_type_and_interface_names(knowledge)
        unit = {
            "id": "U-test",
            "file": "test.md",
            "line_start": 1,
            "line_end": 1,
            "type": "table_row",
            "text": "| `TotallyFakeInterfaceType` | An interface that does not exist anywhere |",
        }
        result = tac.verify_unit(
            unit, knowledge, [], [], {}, None, [],
            method_index={"unrelated_method": ["SomeClass"]},
            platform="net", type_names=type_names,
        )
        self.assertEqual(result["verdict"], tac.VERDICT_FABRICATED)

    def test_qualified_property_type_not_reinterpreted_as_member(self):
        """Live cells/java regression: a nested property type is not a
        nonexistent member of its qualifying class."""
        knowledge = self._make_knowledge()
        knowledge.classes["AutoFilterModel"] = {}
        knowledge.property_types = {
            ("AutoFilterCustomFilter", "operator"):
                "AutoFilterModel.FilterOperatorType",
        }
        type_names = tac._build_type_and_interface_names(knowledge)
        unit = {
            "id": "U-test",
            "file": "AutoFilterCustomFilter.md",
            "line_start": 55,
            "line_end": 55,
            "type": "table_row",
            "text": "| `operator` | `AutoFilterModel.FilterOperatorType` | Read | Returns the operator. |",
        }
        result = tac.verify_unit(
            unit,
            knowledge,
            [],
            [],
            {},
            None,
            [],
            method_index={"operator": ["AutoFilterCustomFilter"]},
            platform="java",
            type_names=type_names,
        )
        self.assertNotEqual(result["verdict"], tac.VERDICT_FABRICATED)

    def test_java_framework_types_do_not_create_fabrication(self):
        """Live cells/java regressions: JDK types in prose/tables are outside
        the product API and therefore cannot prove product fabrication."""
        knowledge = self._make_knowledge()
        method_index = {
            "getCount": ["WorksheetCollection"],
            "unrelatedMethod": ["SomeClass"],
        }
        for text in (
            "| `get(index)` throws `IndexOutOfBoundsException` | "
            "Sheet index beyond `getCount() - 1` |",
            "Always wrap the `InputStream` in a try-with-resources block "
            "so the stream is closed even if the constructor throws.",
        ):
            unit = {
                "id": "U-test",
                "file": "test.md",
                "line_start": 1,
                "line_end": 1,
                "type": "table_row" if text.startswith("|") else "paragraph",
                "text": text,
            }
            result = tac.verify_unit(
                unit,
                knowledge,
                [],
                [],
                {},
                None,
                [],
                method_index=method_index,
                platform="java",
                type_names=set(),
            )
            self.assertNotEqual(result["verdict"], tac.VERDICT_FABRICATED)


class TestLoadFormatsMerge(unittest.TestCase):
    """Root cause (found 2026-07-23): _load_formats() overwrote result[ext]
    per raw formats.json entry with no merge logic, so whichever entry
    happened to appear LAST in the array silently won -- a format with
    separate import-direction and export-direction entries (e.g. Text: one
    LoadFormat entry direction=import, one SaveFormat entry direction=export)
    resolved to whichever direction was listed last, not "both". Confirmed
    live: words/net's Text/Txt formats (both import- and export-capable)
    triggered a false CONTRADICTED verdict on TxtLeadingSpacesOptions.md
    correctly describing IMPORT behavior, because the last entry in
    formats.json happened to be an export-direction one.
    """

    def _write_formats(self, tmp_path, entries):
        merged = tmp_path / "words" / "net" / "merged"
        merged.mkdir(parents=True)
        (merged / "formats.json").write_text(json.dumps(entries), encoding="utf-8")

    def test_import_then_export_merges_to_both(self):
        import tempfile
        with tempfile.TemporaryDirectory() as td:
            tmp_path = Path(td)
            self._write_formats(tmp_path, [
                {"format": "Text", "direction": "import"},
                {"format": "Text", "direction": "export"},
            ])
            with patch.object(tac, "KNOWLEDGE_ROOT", tmp_path):
                result = tac._load_formats("words", "net")
            self.assertEqual(result["text"], "both")

    def test_export_then_import_merges_to_both(self):
        """Order must not matter -- the bug was specifically order-dependent."""
        import tempfile
        with tempfile.TemporaryDirectory() as td:
            tmp_path = Path(td)
            self._write_formats(tmp_path, [
                {"format": "Txt", "direction": "export"},
                {"format": "Txt", "direction": "import"},
                {"format": "Txt", "direction": "export"},
                {"format": "Txt", "direction": "import"},
            ])
            with patch.object(tac, "KNOWLEDGE_ROOT", tmp_path):
                result = tac._load_formats("words", "net")
            self.assertEqual(result["txt"], "both")

    def test_single_direction_unaffected(self):
        import tempfile
        with tempfile.TemporaryDirectory() as td:
            tmp_path = Path(td)
            self._write_formats(tmp_path, [
                {"format": "Fbx", "direction": "export"},
            ])
            with patch.object(tac, "KNOWLEDGE_ROOT", tmp_path):
                result = tac._load_formats("words", "net")
            self.assertEqual(result["fbx"], "export")

    def test_none_direction_does_not_override_real_direction(self):
        import tempfile
        with tempfile.TemporaryDirectory() as td:
            tmp_path = Path(td)
            self._write_formats(tmp_path, [
                {"format": "Html", "direction": "import"},
                {"format": "Html", "direction": "none"},
            ])
            with patch.object(tac, "KNOWLEDGE_ROOT", tmp_path):
                result = tac._load_formats("words", "net")
            self.assertEqual(result["html"], "import")


class TestClassifyUnit(unittest.TestCase):
    """Change B: Unit classification into claim vs structural/code/reference."""

    def test_classify_heading_structural(self):
        unit = {"type": "heading", "text": "Getting Started with Document Processing"}
        self.assertEqual(tac.classify_unit(unit), tac.CLAIM_TYPE_STRUCTURAL)

    def test_classify_code_block_code(self):
        unit = {"type": "code_block", "text": "from aspose.words import Document\ndoc = Document()"}
        self.assertEqual(tac.classify_unit(unit), tac.CLAIM_TYPE_CODE)

    def test_classify_table_header_structural(self):
        unit = {"type": "table_row", "text": "| Name | Type | Description |"}
        self.assertEqual(tac.classify_unit(unit), tac.CLAIM_TYPE_STRUCTURAL)

    def test_classify_table_with_api_ref_claim(self):
        unit = {"type": "table_row", "text": "| `Document.save()` | Saves the document to disk |"}
        self.assertEqual(tac.classify_unit(unit), tac.CLAIM_TYPE_CLAIM)

    def test_classify_nav_link_reference(self):
        unit = {"type": "list_item", "text": "- [Core Management](/docs/words/python/core/) — learn how to manage"}
        self.assertEqual(tac.classify_unit(unit), tac.CLAIM_TYPE_REFERENCE)

    def test_classify_paragraph_with_api_claim(self):
        unit = {"type": "paragraph", "text": "The `Document.save` method writes the file to the specified path."}
        self.assertEqual(tac.classify_unit(unit), tac.CLAIM_TYPE_CLAIM)

    def test_classify_short_boilerplate_structural(self):
        unit = {"type": "paragraph", "text": "Code block style preference."}
        self.assertEqual(tac.classify_unit(unit), tac.CLAIM_TYPE_STRUCTURAL)

    def test_classify_multiword_bold_dash_reference(self):
        """Multi-word bold terms like **Commercial use** should be reference."""
        unit = {"type": "list_item", "text": "- **Commercial use** — integrate the library into paid products"}
        self.assertEqual(tac.classify_unit(unit), tac.CLAIM_TYPE_REFERENCE)

    def test_classify_singleword_bold_dash_still_reference(self):
        """Single-word bold terms still match (no regression)."""
        unit = {"type": "list_item", "text": "- **Modify** — make changes to the source"}
        self.assertEqual(tac.classify_unit(unit), tac.CLAIM_TYPE_REFERENCE)


class TestSummaryMetrics(unittest.TestCase):
    """Change C: Summary includes claim_verification_rate and confidence_bands."""

    def test_summary_includes_claim_rate(self):
        """Simulated summary must contain claim_units and claim_verification_rate."""
        # Build minimal units with claim_type and verdict fields
        units = [
            {"verdict": tac.VERDICT_VERIFIED, "claim_type": tac.CLAIM_TYPE_CLAIM, "confidence": 0.8},
            {"verdict": tac.VERDICT_VERIFIED, "claim_type": tac.CLAIM_TYPE_CLAIM, "confidence": 0.5},
            {"verdict": tac.VERDICT_UNVERIFIABLE, "claim_type": tac.CLAIM_TYPE_STRUCTURAL, "confidence": 0.0},
            {"verdict": tac.VERDICT_UNVERIFIABLE, "claim_type": tac.CLAIM_TYPE_CODE, "confidence": 0.0},
            {"verdict": tac.VERDICT_UNSUPPORTED, "claim_type": tac.CLAIM_TYPE_CLAIM, "confidence": 0.1},
        ]
        claim_units = sum(1 for u in units if u.get("claim_type") == tac.CLAIM_TYPE_CLAIM)
        verified = sum(1 for u in units if u.get("verdict") == tac.VERDICT_VERIFIED)
        self.assertEqual(claim_units, 3)
        self.assertEqual(verified, 2)
        # claim_verification_rate = 2/3 ≈ 0.667
        rate = round(verified / claim_units, 3)
        self.assertAlmostEqual(rate, 0.667, places=3)
        # Confidence bands
        high = sum(1 for u in units if u.get("verdict") == tac.VERDICT_VERIFIED and u.get("confidence", 0) >= 0.7)
        medium = sum(1 for u in units if u.get("verdict") == tac.VERDICT_VERIFIED and 0.5 <= u.get("confidence", 0) < 0.7)
        self.assertEqual(high, 1)
        self.assertEqual(medium, 1)


class TestApiRefRegex(unittest.TestCase):
    """SR-07/G-08: _API_REF_RE must handle parens and dotted refs."""

    def test_simple_identifier(self):
        self.assertEqual(tac._API_REF_RE.findall("`Document`"), ["Document"])

    def test_dotted_identifier(self):
        self.assertEqual(tac._API_REF_RE.findall("`Document.save`"), ["Document.save"])

    def test_method_with_empty_parens(self):
        self.assertEqual(tac._API_REF_RE.findall("`Document.save()`"), ["Document.save"])

    def test_method_with_args(self):
        self.assertEqual(tac._API_REF_RE.findall("`Document.save(path)`"), ["Document.save"])

    def test_bare_method_with_parens(self):
        self.assertEqual(tac._API_REF_RE.findall("`is_ordered_list()`"), ["is_ordered_list"])

    def test_no_match_expression(self):
        """Expressions like `a + b` should not match."""
        self.assertEqual(tac._API_REF_RE.findall("`a + b`"), [])

    def test_multiple_refs_in_text(self):
        text = "Use `Document.save()` and `PdfSaveOptions` together."
        self.assertEqual(sorted(tac._API_REF_RE.findall(text)),
                         ["Document.save", "PdfSaveOptions"])

    def test_method_with_multiple_args(self):
        self.assertEqual(tac._API_REF_RE.findall("`save(path, format)`"), ["save"])


# ---------------------------------------------------------------------------
# Anti-regression: _find_clone_cache must never probe foss-launcher paths
# GAP-01 closure
# ---------------------------------------------------------------------------


class TestFindCloneCacheAntiRegression(unittest.TestCase):
    """_find_clone_cache() must use runs/.clone_cache/, never foss-launcher.

    GAP-01: no automated guard existed for this function.  These tests ensure
    that future edits cannot silently reintroduce an obsolete foss-launcher
    clone-cache base without causing a test failure.
    """

    def test_search_base_is_runs_clone_cache_not_foss_launcher(self):
        """The module-level canonical base must be repo-root/runs/.clone_cache."""
        repo_root = tac._REPO_ROOT
        canonical_base = repo_root / "runs" / ".clone_cache"
        base_str = str(canonical_base).replace("\\", "/").lower()
        self.assertIn("runs/.clone_cache", base_str)
        self.assertNotIn("foss-launcher", base_str)  # TEST_FIXTURE_OBSOLETE_FOSS_LAUNCHER_REFERENCE
        self.assertNotIn("foss_launcher", base_str)  # TEST_FIXTURE_OBSOLETE_FOSS_LAUNCHER_REFERENCE

    def test_find_clone_cache_returns_none_for_nonexistent_product(self):
        """Missing clone returns None, not a foss-launcher path."""
        result = tac._find_clone_cache("no_such_family_xyzzy", "no_such_platform_xyzzy")
        self.assertIsNone(result)

    def test_find_clone_cache_result_uses_canonical_base(self):
        """When a clone exists the returned path is under runs/.clone_cache/."""
        with tempfile.TemporaryDirectory() as tmp:
            tmp_root = Path(tmp)
            cache_dir = tmp_root / "runs" / ".clone_cache" / "aspose_testfam_testplat"
            cache_dir.mkdir(parents=True)
            orig_root = tac._REPO_ROOT
            try:
                tac._REPO_ROOT = tmp_root
                result = tac._find_clone_cache("testfam", "testplat")
                self.assertIsNotNone(result, "Expected clone cache found under patched root")
                result_str = str(result).replace("\\", "/").lower()
                self.assertIn("runs/.clone_cache", result_str)
                self.assertNotIn("foss-launcher", result_str)  # TEST_FIXTURE_OBSOLETE_FOSS_LAUNCHER_REFERENCE
                self.assertNotIn("foss_launcher", result_str)  # TEST_FIXTURE_OBSOLETE_FOSS_LAUNCHER_REFERENCE
            finally:
                tac._REPO_ROOT = orig_root


if __name__ == "__main__":
    unittest.main()
