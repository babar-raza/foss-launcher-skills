"""Tests for audit.runner.verify_faq_structure — faq.list frontmatter FAIL rule.

Four cases:
  (a) faq.list non-empty + no check_evidence guard bypass concern → FAIL finding
  (b) no faq.list key → no finding
  (c) faq.list present but empty list → no finding
  (d) check fires even when check_evidence=False (via audit_files)
"""
import tempfile
import unittest
from pathlib import Path
from unittest.mock import MagicMock, patch

# sys.path is set by tests/conftest.py — no manual insert needed here.
from audit import Finding, verify_faq_structure
from audit.runner import audit_files


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _make_file(content: str) -> Path:
    """Write content to a temp .md file and return its Path."""
    f = tempfile.NamedTemporaryFile(
        mode="w", suffix=".md", delete=False, encoding="utf-8"
    )
    f.write(content)
    f.close()
    return Path(f.name)


_FAQ_LIST_FRONTMATTER = """\
---
title: FAQ
type: topic
faq:
  list:
  - question: How do I install?
    answer: Run pip install.
  - question: What formats are supported?
    answer: XLSX, CSV, PDF.
---

## Overview

Some body content with no ### headings.
"""

_NO_FAQ_FRONTMATTER = """\
---
title: Regular page
type: topic
---

## Overview

Body content.
"""

_EMPTY_FAQ_LIST_FRONTMATTER = """\
---
title: FAQ
type: topic
faq:
  list: []
---

## Overview

Body content.
"""


# ---------------------------------------------------------------------------
# TestVerifyFaqStructure — pure unit tests (no filesystem required for (a-c))
# ---------------------------------------------------------------------------

class TestVerifyFaqStructure(unittest.TestCase):

    # (a) faq.list non-empty → FAIL finding emitted
    def test_faq_list_nonempty_emits_fail(self):
        fp = _make_file(_FAQ_LIST_FRONTMATTER)
        fm = {"faq": {"list": [{"question": "Q1", "answer": "A1"},
                                {"question": "Q2", "answer": "A2"}]}}
        findings = verify_faq_structure(fp, fm)
        self.assertEqual(len(findings), 1)
        f = findings[0]
        self.assertIsInstance(f, Finding)
        self.assertEqual(f.level, "FAIL")
        self.assertIn("faq.list", f.message)
        self.assertIn("invisible to users", f.message)
        self.assertIn("2 entries", f.message)
        self.assertIn("/new-kb-faq", f.suggestion)

    # (b) no faq key → no finding
    def test_no_faq_key_returns_empty(self):
        fp = Path("fake.md")
        fm = {"title": "Something", "type": "topic"}
        findings = verify_faq_structure(fp, fm)
        self.assertEqual(findings, [])

    # (c) faq.list is empty list → no finding
    def test_empty_faq_list_returns_empty(self):
        fp = Path("fake.md")
        fm = {"faq": {"list": []}}
        findings = verify_faq_structure(fp, fm)
        self.assertEqual(findings, [])

    # edge: faq key present but no 'list' sub-key → no finding
    def test_faq_key_without_list_returns_empty(self):
        fp = Path("fake.md")
        fm = {"faq": {}}
        findings = verify_faq_structure(fp, fm)
        self.assertEqual(findings, [])

    # filepath is stored as string in Finding.filepath
    def test_filepath_stored_as_string(self):
        fp = _make_file(_FAQ_LIST_FRONTMATTER)
        fm = {"faq": {"list": [{"question": "Q", "answer": "A"}]}}
        findings = verify_faq_structure(fp, fm)
        self.assertEqual(len(findings), 1)
        self.assertIsInstance(findings[0].filepath, str)
        self.assertEqual(findings[0].filepath, str(fp))


# ---------------------------------------------------------------------------
# TestAuditFilesFaqGate — integration test: check fires regardless of check_evidence
# ---------------------------------------------------------------------------

class TestAuditFilesFaqGate(unittest.TestCase):
    """Verify verify_faq_structure is called from audit_files even when
    check_evidence=False.  We mock out verify_tokens, verify_evidence,
    verify_internal_links, and infer_product to isolate the faq gate.
    """

    def _run_audit_files_no_evidence(self, content: str):
        """Run audit_files with check_evidence=False on a single temp file."""
        fp = _make_file(content)

        mock_knowledge = MagicMock()
        mock_knowledge.available = True

        with (
            patch("audit.runner.infer_product", return_value=("cells", "net")),
            patch("audit.runner.Knowledge", return_value=mock_knowledge),
            patch("audit.runner.extract_tokens", return_value=[]),
            patch("audit.runner.verify_tokens", return_value=[]),
            patch("audit.runner.verify_evidence", return_value=[]),
            patch("audit.runner.verify_internal_links", return_value=[]),
        ):
            return audit_files([str(fp)], check_evidence=False)

    # (d) faq.list present, check_evidence=False → FAIL still fires
    def test_faq_fail_fires_when_check_evidence_false(self):
        findings = self._run_audit_files_no_evidence(_FAQ_LIST_FRONTMATTER)
        fail_findings = [f for f in findings if f.level == "FAIL" and "faq.list" in f.message]
        self.assertEqual(
            len(fail_findings), 1,
            f"Expected 1 faq.list FAIL but got {len(fail_findings)}. All findings: {findings}"
        )

    # regression: clean page, check_evidence=False → no faq.list FAIL
    def test_clean_page_no_faq_fail_when_check_evidence_false(self):
        findings = self._run_audit_files_no_evidence(_NO_FAQ_FRONTMATTER)
        faq_fails = [f for f in findings if "faq.list" in getattr(f, "message", "")]
        self.assertEqual(len(faq_fails), 0)

    # regression: empty faq.list, check_evidence=False → no FAIL
    def test_empty_faq_list_no_fail_when_check_evidence_false(self):
        findings = self._run_audit_files_no_evidence(_EMPTY_FAQ_LIST_FRONTMATTER)
        faq_fails = [f for f in findings if "faq.list" in getattr(f, "message", "")]
        self.assertEqual(len(faq_fails), 0)


if __name__ == "__main__":
    unittest.main()
