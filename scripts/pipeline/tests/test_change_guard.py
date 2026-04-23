"""Regression tests for change_guard.py."""

from __future__ import annotations

import json
import shutil
import sys
import tempfile
import unittest
from contextlib import contextmanager
from pathlib import Path


_PIPELINE_DIR = Path(__file__).resolve().parent.parent
if str(_PIPELINE_DIR) not in sys.path:
    sys.path.insert(0, str(_PIPELINE_DIR))

import change_guard  # noqa: E402
from change_guard import DECISION_DENY, DECISION_PASS, _parse_not_implemented, guard_text  # noqa: E402


_FIXTURES_DIR = Path(__file__).resolve().parent / "fixtures"


@contextmanager
def fake_knowledge_dir():
    """Build a complete fake knowledge dir including install and index artifacts."""
    import knowledge_core

    with tempfile.TemporaryDirectory() as temp_dir:
        root = Path(temp_dir)
        merged = root / "knowledge" / "fake" / "python" / "merged"
        merged.mkdir(parents=True)

        for fname in (
            "fake_api_surface.json",
            "fake_model.yaml",
            "fake_claims.json",
            "fake_formats.json",
        ):
            dest = fname.replace("fake_", "")
            shutil.copy(_FIXTURES_DIR / fname, merged / dest)

        shutil.copy(_FIXTURES_DIR / "fake_index.json", merged / "index.json")
        (merged / "install.md").write_text("pip install aspose-fake-foss\n", encoding="utf-8")

        original_kc = knowledge_core._KNOWLEDGE_ROOT
        change_guard.configure(repo_root=root)
        knowledge_core._KNOWLEDGE_ROOT = root / "knowledge"
        try:
            yield root / "knowledge"
        finally:
            change_guard.configure()
            knowledge_core._KNOWLEDGE_ROOT = original_kc


class ParseNotImplementedTests(unittest.TestCase):
    def test_extracts_class_member_pairs(self):
        forbidden = [
            "supports Node.get_bounding_box",
            "supports Scene.broken_method",
            "other unrelated claim",
        ]
        result = _parse_not_implemented(forbidden)
        self.assertIn(("Node", "get_bounding_box"), result)
        self.assertIn(("Scene", "broken_method"), result)

    def test_empty_list(self):
        self.assertEqual(_parse_not_implemented([]), set())

    def test_ignores_non_matching_strings(self):
        self.assertEqual(_parse_not_implemented(["no dot here", "also no match"]), set())

    def test_case_insensitive_verb(self):
        result = _parse_not_implemented(["Supports Entity.some_method"])
        self.assertIn(("Entity", "some_method"), result)


class GuardTextNotImplementedTests(unittest.TestCase):
    def test_backtick_not_implemented_is_deny(self):
        with fake_knowledge_dir():
            result = guard_text(
                "Call `Node.get_bounding_box` to compute the bounding box.",
                "fake",
                "python",
            )
        self.assertEqual(result["decision"], DECISION_DENY)
        self.assertTrue(any(issue["check"] == "not_implemented" for issue in result["issues"]))
        self.assertFalse(result["has_evidence"])

    def test_prose_not_implemented_is_deny(self):
        with fake_knowledge_dir():
            result = guard_text(
                "The Node class supports get_bounding_box for computing bounds.",
                "fake",
                "python",
            )
        self.assertEqual(result["decision"], DECISION_DENY)

    def test_second_forbidden_backtick_is_deny(self):
        with fake_knowledge_dir():
            result = guard_text(
                "Use `Scene.broken_method` to do something.",
                "fake",
                "python",
            )
        self.assertEqual(result["decision"], DECISION_DENY)
        deny_checks = {
            issue["check"] for issue in result["issues"] if issue["decision"] == DECISION_DENY
        }
        self.assertTrue(deny_checks & {"not_implemented", "api_reference"})


class GuardTextValidMethodsTests(unittest.TestCase):
    def test_valid_method_is_pass(self):
        with fake_knowledge_dir():
            result = guard_text(
                "Use `Scene.open` to load a file from disk.",
                "fake",
                "python",
            )
        self.assertEqual(result["decision"], DECISION_PASS)
        self.assertTrue(result["has_evidence"])

    def test_valid_property_is_pass(self):
        with fake_knowledge_dir():
            result = guard_text(
                "Access `Scene.root_node` to get the scene root.",
                "fake",
                "python",
            )
        self.assertEqual(result["decision"], DECISION_PASS)
        self.assertTrue(result["has_evidence"])

    def test_nonexistent_member_is_deny(self):
        with fake_knowledge_dir():
            result = guard_text(
                "Call `Scene.does_not_exist` to perform an operation.",
                "fake",
                "python",
            )
        self.assertEqual(result["decision"], DECISION_DENY)
        self.assertTrue(any(issue["check"] == "api_reference" for issue in result["issues"]))


class GuardTextUnknownAndOperationalClaimsTests(unittest.TestCase):
    def test_unknown_class_is_deny(self):
        with fake_knowledge_dir():
            result = guard_text(
                "Call `MadeUpClass.some_method` to do something.",
                "fake",
                "python",
            )
        self.assertEqual(result["decision"], DECISION_DENY)
        self.assertTrue(any(issue["check"] == "api_reference" for issue in result["issues"]))

    def test_fake_install_package_is_deny(self):
        with fake_knowledge_dir():
            result = guard_text(
                "Install it with `pip install made-up-package` before use.",
                "fake",
                "python",
            )
        self.assertEqual(result["decision"], DECISION_DENY)
        self.assertTrue(any(issue["check"] == "install_package" for issue in result["issues"]))

    def test_false_office_prerequisite_is_deny(self):
        with fake_knowledge_dir():
            result = guard_text(
                "The library requires Microsoft Office to export documents.",
                "fake",
                "python",
            )
        self.assertEqual(result["decision"], DECISION_DENY)
        self.assertTrue(any(issue["check"] == "prerequisite" for issue in result["issues"]))


class GuardTextFormatDirectionTests(unittest.TestCase):
    def test_export_of_import_only_format_is_deny(self):
        with fake_knowledge_dir() as knowledge_root:
            fmts_path = knowledge_root / "fake" / "python" / "merged" / "formats.json"
            formats = json.loads(fmts_path.read_text(encoding="utf-8"))
            import_only = [
                fmt for fmt in formats
                if (fmt.get("direction") or fmt.get("support") or "").lower() == "import"
            ]
            if not import_only:
                self.skipTest("No import-only formats in fixture")

            ext = (import_only[0].get("format") or import_only[0].get("ext") or "").lower()
            result = guard_text(
                f"You can export the {ext} format using this method.",
                "fake",
                "python",
            )
        self.assertEqual(result["decision"], DECISION_DENY)


if __name__ == "__main__":
    unittest.main()
