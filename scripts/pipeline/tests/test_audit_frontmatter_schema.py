"""Tests for audit.frontmatter_schema.verify_no_explicit_url — explicit
url: frontmatter key FAIL rule (ASPOSE-URL-FRONTMATTER-COLLISION-
REMEDIATION, TC-URL-005 / REQ-URL-003).

Cases:
  (a) top-level url: key present → FAIL finding
  (b) no url: key → no finding
  (c) url: mentioned only in the markdown body (not frontmatter) → no finding
  (d) url: appears as a nested/indented key under another frontmatter block
      → no finding (top-level-only detection is the confirmed-sufficient
      design; see module docstring in frontmatter_schema.py)
  (e) file with no frontmatter block at all → no finding, no crash
  (f) check fires even when check_evidence=False (via audit_files)
  (g) audit_product() path wires verify_no_explicit_url
"""
import tempfile
import unittest
from pathlib import Path
from unittest.mock import MagicMock, patch

# sys.path is set by tests/conftest.py — no manual insert needed here.
from audit import Finding, verify_no_explicit_url
from audit.runner import audit_files, audit_product


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


_EXPLICIT_URL_FRONTMATTER = """\
---
title: Installation
type: docs
url: /cells/java/getting-started/installation/
weight: 11
---

## Overview

Some body content.
"""

_NO_URL_FRONTMATTER = """\
---
title: Installation
type: docs
weight: 11
---

## Overview

Body content.
"""

_URL_ONLY_IN_BODY = """\
---
title: Installation
type: docs
---

## See Also

Visit url: https://docs.aspose.org/ for more information.
"""

_NESTED_URL_KEY = """\
---
title: Page with menu
menu:
  main:
    url: /some/path/
---

## Overview

Body content.
"""

_NO_FRONTMATTER_AT_ALL = """\
# Just a heading

No frontmatter block here at all.
"""


# ---------------------------------------------------------------------------
# TestVerifyNoExplicitUrl — pure unit tests
# ---------------------------------------------------------------------------

class TestVerifyNoExplicitUrl(unittest.TestCase):

    # (a) top-level url: key present → FAIL finding emitted
    def test_explicit_url_key_emits_fail(self):
        fp = _make_file(_EXPLICIT_URL_FRONTMATTER)
        findings = verify_no_explicit_url(fp)
        self.assertEqual(len(findings), 1)
        f = findings[0]
        self.assertIsInstance(f, Finding)
        self.assertEqual(f.level, "FAIL")
        self.assertIn("url:", f.message)
        self.assertIn("Hugo derives", f.suggestion)

    # (b) no url: key → no finding
    def test_no_url_key_returns_empty(self):
        fp = _make_file(_NO_URL_FRONTMATTER)
        findings = verify_no_explicit_url(fp)
        self.assertEqual(findings, [])

    # (c) "url:" appears only in body prose, never in frontmatter → no finding
    def test_url_mentioned_in_body_only_returns_empty(self):
        fp = _make_file(_URL_ONLY_IN_BODY)
        findings = verify_no_explicit_url(fp)
        self.assertEqual(findings, [])

    # (d) url: as a nested/indented key under another block → no finding
    # (top-level-only detection is the confirmed-sufficient design)
    def test_nested_url_key_returns_empty(self):
        fp = _make_file(_NESTED_URL_KEY)
        findings = verify_no_explicit_url(fp)
        self.assertEqual(findings, [])

    # (e) no frontmatter block at all → no finding, no crash
    def test_no_frontmatter_block_returns_empty(self):
        fp = _make_file(_NO_FRONTMATTER_AT_ALL)
        findings = verify_no_explicit_url(fp)
        self.assertEqual(findings, [])

    # line_no points at the actual url: line, not line 1
    def test_line_number_matches_url_line(self):
        fp = _make_file(_EXPLICIT_URL_FRONTMATTER)
        findings = verify_no_explicit_url(fp)
        self.assertEqual(len(findings), 1)
        # url: is line 4 in _EXPLICIT_URL_FRONTMATTER (1-indexed)
        self.assertEqual(findings[0].line_no, 4)

    # filepath is stored as string in Finding.filepath (consistent with
    # verify_maven_coordinates / verify_faq_structure conventions)
    def test_filepath_stored_consistently(self):
        fp = _make_file(_EXPLICIT_URL_FRONTMATTER)
        findings = verify_no_explicit_url(fp)
        self.assertEqual(len(findings), 1)
        self.assertEqual(findings[0].filepath, fp)

    # nonexistent file → no crash, empty findings (same contract as
    # verify_maven_coordinates)
    def test_nonexistent_file_returns_empty(self):
        findings = verify_no_explicit_url(Path("does-not-exist-xyz.md"))
        self.assertEqual(findings, [])


# ---------------------------------------------------------------------------
# TestAuditFilesUrlGate — integration test: check fires regardless of
# check_evidence, matching the FAQ gate's verified wiring pattern
# ---------------------------------------------------------------------------

class TestAuditFilesUrlGate(unittest.TestCase):

    def _run_audit_files_no_evidence(self, content: str):
        fp = _make_file(content)

        mock_knowledge = MagicMock()
        mock_knowledge.available = True

        with (
            patch("audit.runner.infer_product", return_value=("cells", "java")),
            patch("audit.runner.Knowledge", return_value=mock_knowledge),
            patch("audit.runner.extract_tokens", return_value=[]),
            patch("audit.runner.verify_tokens", return_value=[]),
            patch("audit.runner.verify_evidence", return_value=[]),
            patch("audit.runner.verify_internal_links", return_value=[]),
        ):
            return audit_files([str(fp)], check_evidence=False)

    # (f) explicit url:, check_evidence=False → FAIL still fires
    def test_url_fail_fires_when_check_evidence_false(self):
        findings = self._run_audit_files_no_evidence(_EXPLICIT_URL_FRONTMATTER)
        fail_findings = [f for f in findings if f.level == "FAIL" and "url:" in f.message]
        self.assertEqual(
            len(fail_findings), 1,
            f"Expected 1 url: FAIL but got {len(fail_findings)}. All findings: {findings}"
        )

    # regression: clean page, check_evidence=False → no url: FAIL
    def test_clean_page_no_url_fail_when_check_evidence_false(self):
        findings = self._run_audit_files_no_evidence(_NO_URL_FRONTMATTER)
        url_fails = [f for f in findings if "url:" in getattr(f, "message", "")]
        self.assertEqual(url_fails, [])


# ---------------------------------------------------------------------------
# TestAuditProductUrlGate — audit_product() path wires verify_no_explicit_url
# ---------------------------------------------------------------------------

class TestAuditProductUrlGate(unittest.TestCase):

    def test_url_fail_fires_via_audit_product(self):
        fp = _make_file(_EXPLICIT_URL_FRONTMATTER)

        mock_knowledge = MagicMock()
        mock_knowledge.available = True
        mock_knowledge.surface_tier = "T1"

        with (
            patch("audit.runner.Knowledge", return_value=mock_knowledge),
            patch("audit.runner.discover_content", return_value=[fp]),
            patch("audit.runner.extract_tokens", return_value=[]),
            patch("audit.runner.verify_tokens", return_value=[]),
            patch("audit.runner.verify_evidence", return_value=[]),
            patch("audit.runner.verify_internal_links", return_value=[]),
        ):
            findings = audit_product("cells", "java", check_evidence=False)

        fail_findings = [f for f in findings if f.level == "FAIL" and "url:" in f.message]
        self.assertEqual(
            len(fail_findings), 1,
            f"Expected 1 url: FAIL via audit_product but got {len(fail_findings)}"
        )

    def test_clean_page_no_url_fail_via_audit_product(self):
        fp = _make_file(_NO_URL_FRONTMATTER)

        mock_knowledge = MagicMock()
        mock_knowledge.available = True
        mock_knowledge.surface_tier = "T1"

        with (
            patch("audit.runner.Knowledge", return_value=mock_knowledge),
            patch("audit.runner.discover_content", return_value=[fp]),
            patch("audit.runner.extract_tokens", return_value=[]),
            patch("audit.runner.verify_tokens", return_value=[]),
            patch("audit.runner.verify_evidence", return_value=[]),
            patch("audit.runner.verify_internal_links", return_value=[]),
        ):
            findings = audit_product("cells", "java", check_evidence=False)

        url_fails = [f for f in findings if "url:" in getattr(f, "message", "")]
        self.assertEqual(url_fails, [])


if __name__ == "__main__":
    unittest.main()
