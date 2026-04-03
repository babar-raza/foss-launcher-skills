"""Unit tests for validate_frontmatter.py using temp files."""

from __future__ import annotations

import json
import shutil
import sys
import tempfile
import textwrap
from pathlib import Path

import pytest

_PIPELINE_ROOT = Path(__file__).resolve().parent.parent
if str(_PIPELINE_ROOT) not in sys.path:
    sys.path.insert(0, str(_PIPELINE_ROOT))

from validate_frontmatter import check_file, main  # noqa: E402


def _tmp_md(content: str) -> Path:
    """Write content to a temp .md file and return its path."""
    f = tempfile.NamedTemporaryFile(suffix=".md", mode="w", encoding="utf-8", delete=False)
    f.write(textwrap.dedent(content))
    f.close()
    return Path(f.name)


CLEAN_FILE = """\
---
title: Valid Page
type: docs
weight: 10
---
Body text.
"""


class TestCleanFiles:
    def test_valid_frontmatter_passes(self):
        p = _tmp_md(CLEAN_FILE)
        try:
            assert check_file(p) == []
        finally:
            p.unlink(missing_ok=True)

    def test_no_frontmatter_passes(self):
        p = _tmp_md("Just plain text, no frontmatter.\n")
        try:
            assert check_file(p) == []
        finally:
            p.unlink(missing_ok=True)

    def test_empty_file_passes(self):
        p = _tmp_md("")
        try:
            assert check_file(p) == []
        finally:
            p.unlink(missing_ok=True)


class TestDuplicateKeys:
    def test_duplicate_top_level_key_detected(self):
        p = _tmp_md("""\
        ---
        title: First
        title: Second
        type: docs
        ---
        Body.
        """)
        try:
            errors = check_file(p)
            checks = [e.check for e in errors]
            assert "duplicate_key" in checks
        finally:
            p.unlink(missing_ok=True)

    def test_duplicate_grade_key_detected(self):
        p = _tmp_md("""\
        ---
        title: Dup
        grade: A
        graded_at: "2026-01-01"
        graded_evaluators: full
        graded_evaluators: audit
        ---
        Body.
        """)
        try:
            errors = check_file(p)
            keys = [e.check for e in errors]
            assert "duplicate_key" in keys
            assert any("graded_evaluators" in e.detail for e in errors)
        finally:
            p.unlink(missing_ok=True)

    def test_unique_keys_no_error(self):
        p = _tmp_md("""\
        ---
        title: Clean
        grade: A
        graded_at: "2026-01-01"
        graded_evaluators: full
        ---
        Body.
        """)
        try:
            assert check_file(p) == []
        finally:
            p.unlink(missing_ok=True)


class TestDoubleFrontmatter:
    def test_double_frontmatter_detected(self):
        """Two separate --- blocks at the top is a structural error."""
        content = (
            "---\n"
            "provenance:\n"
            "  translation_origin: translator\n"
            "---\n"
            "\n"
            "---\n"
            "title: Real Title\n"
            "type: docs\n"
            "---\n"
            "Body.\n"
        )
        p = _tmp_md(content)
        try:
            errors = check_file(p)
            checks = [e.check for e in errors]
            assert "double_frontmatter" in checks
        finally:
            p.unlink(missing_ok=True)

    def test_double_frontmatter_reports_second_block_key(self):
        """Error message hints at the first key in the second block."""
        content = (
            "---\n"
            "provenance:\n"
            "  translation_origin: translator\n"
            "---\n"
            "\n"
            "---\n"
            "layout: family\n"
            "title: Something\n"
            "---\n"
            "Body.\n"
        )
        p = _tmp_md(content)
        try:
            errors = check_file(p)
            double = [e for e in errors if e.check == "double_frontmatter"]
            assert double, "Expected double_frontmatter error"
            assert "layout" in double[0].detail
        finally:
            p.unlink(missing_ok=True)

    def test_single_frontmatter_no_error(self):
        """File with one --- block and body containing dashes does not trigger."""
        content = (
            "---\n"
            "title: Dashes in body\n"
            "---\n"
            "Some text with --- in a line.\n"
            "More text.\n"
        )
        p = _tmp_md(content)
        try:
            assert check_file(p) == []
        finally:
            p.unlink(missing_ok=True)


class TestCLI:
    def test_clean_file_exits_0(self):
        p = _tmp_md(CLEAN_FILE)
        try:
            assert main([str(p)]) == 0
        finally:
            p.unlink(missing_ok=True)

    def test_duplicate_key_exits_1(self):
        p = _tmp_md("""\
        ---
        title: X
        title: Y
        ---
        Body.
        """)
        try:
            assert main([str(p)]) == 1
        finally:
            p.unlink(missing_ok=True)

    def test_double_frontmatter_exits_1(self):
        content = (
            "---\n"
            "provenance:\n"
            "  translation_origin: translator\n"
            "---\n"
            "\n"
            "---\n"
            "title: Real\n"
            "---\n"
            "Body.\n"
        )
        p = _tmp_md(content)
        try:
            assert main([str(p)]) == 1
        finally:
            p.unlink(missing_ok=True)

    def test_json_output(self, capsys):
        p = _tmp_md("""\
        ---
        title: X
        title: Y
        ---
        Body.
        """)
        try:
            main([str(p), "--json"])
            data = json.loads(capsys.readouterr().out)
            assert isinstance(data, list)
            assert len(data) >= 1
            assert data[0]["check"] == "duplicate_key"
        finally:
            p.unlink(missing_ok=True)


def _blog_file(content: str, filename: str = "index.md") -> tuple[Path, Path]:
    """Create a temp file under a blog.aspose.org/{family}/{platform}/{slug}/ path.

    Returns (tmpdir, filepath). Caller must shutil.rmtree(tmpdir) after use.
    The path structure ensures _is_blog_content_file() returns True.
    """
    tmpdir = Path(tempfile.mkdtemp())
    blog_dir = tmpdir / "content" / "blog.aspose.org" / "3d" / "python" / "test-slug"
    blog_dir.mkdir(parents=True)
    p = blog_dir / filename
    p.write_text(textwrap.dedent(content), encoding="utf-8")
    return tmpdir, p


_BLOG_FULL = """\
---
title: Test Blog Post
draft: false
evidence:
  model_sha: abc123
  model_version: 1.0.0
  claims:
  - CLM-001
  apis:
  - Scene.open
provenance:
  content_origin: skill-generated
  last_mechanism: skill
  auto_updatable: true
  reviewed: false
---
Body text.
"""

_BLOG_EMPTY_CLAIMS = """\
---
title: Test Blog Post
draft: false
evidence:
  model_sha: abc123
  model_version: 1.0.0
  claims: []
  apis:
  - Scene.open
---
Body text.
"""

_BLOG_EMPTY_APIS = """\
---
title: Test Blog Post
draft: false
evidence:
  model_sha: abc123
  model_version: 1.0.0
  claims:
  - CLM-001
  apis: []
---
Body text.
"""

_BLOG_MISSING_EVIDENCE = """\
---
title: Test Blog Post
draft: false
---
Body text.
"""

_BLOG_MISSING_DRAFT = """\
---
title: Test Blog Post
evidence:
  model_sha: abc123
  claims:
  - CLM-001
  apis:
  - Scene.open
---
Body text.
"""

_BLOG_MANUAL_REMEDIATION = """\
---
title: Test Blog Post
draft: false
evidence:
  model_sha: abc123
  model_version: 1.0.0
  claims: []
  apis: []
provenance:
  content_origin: manual-remediation
  last_mechanism: agent-edit
  auto_updatable: true
  reviewed: false
---
Body text.
"""


class TestBlogEvidence:
    """Tests for P-03: blog post evidence completeness check.

    These tests verify that:
    - Missing or empty evidence blocks are caught
    - Detail strings reference /evidence-repair for actionable guidance
    - The manual-remediation escape hatch bypasses claims/apis check
    - Locale translation files are excluded from P-03
    - Non-blog files are excluded from P-03
    """

    def test_full_evidence_passes(self):
        """Blog post with all required fields passes P-03."""
        tmpdir, p = _blog_file(_BLOG_FULL)
        try:
            errors = check_file(p)
            blog_errs = [e for e in errors if e.check == "blog_evidence"]
            assert blog_errs == [], f"Unexpected P-03 errors: {blog_errs}"
        finally:
            shutil.rmtree(tmpdir)

    def test_empty_claims_detected(self):
        """Empty evidence.claims fires P-03."""
        tmpdir, p = _blog_file(_BLOG_EMPTY_CLAIMS)
        try:
            errors = check_file(p)
            checks = [e.check for e in errors]
            assert "blog_evidence" in checks
        finally:
            shutil.rmtree(tmpdir)

    def test_empty_apis_detected(self):
        """Empty evidence.apis fires P-03."""
        tmpdir, p = _blog_file(_BLOG_EMPTY_APIS)
        try:
            errors = check_file(p)
            checks = [e.check for e in errors]
            assert "blog_evidence" in checks
        finally:
            shutil.rmtree(tmpdir)

    def test_missing_evidence_block_detected(self):
        """Missing evidence: block fires P-03."""
        tmpdir, p = _blog_file(_BLOG_MISSING_EVIDENCE)
        try:
            errors = check_file(p)
            checks = [e.check for e in errors]
            assert "blog_evidence" in checks
        finally:
            shutil.rmtree(tmpdir)

    def test_missing_draft_field_detected(self):
        """Missing draft: field fires P-03."""
        tmpdir, p = _blog_file(_BLOG_MISSING_DRAFT)
        try:
            errors = check_file(p)
            checks = [e.check for e in errors]
            assert "blog_evidence" in checks
        finally:
            shutil.rmtree(tmpdir)

    def test_empty_claims_detail_includes_evidence_repair_hint(self):
        """Empty claims error detail references /evidence-repair for actionable guidance."""
        tmpdir, p = _blog_file(_BLOG_EMPTY_CLAIMS)
        try:
            errors = check_file(p)
            claims_errs = [e for e in errors if e.check == "blog_evidence" and "claims" in e.detail]
            assert claims_errs, "Expected a blog_evidence error about claims"
            assert "/evidence-repair" in claims_errs[0].detail, (
                f"Expected /evidence-repair in detail, got: {claims_errs[0].detail}"
            )
        finally:
            shutil.rmtree(tmpdir)

    def test_empty_apis_detail_includes_evidence_repair_hint(self):
        """Empty apis error detail references /evidence-repair for actionable guidance."""
        tmpdir, p = _blog_file(_BLOG_EMPTY_APIS)
        try:
            errors = check_file(p)
            apis_errs = [e for e in errors if e.check == "blog_evidence" and "apis" in e.detail]
            assert apis_errs, "Expected a blog_evidence error about apis"
            assert "/evidence-repair" in apis_errs[0].detail, (
                f"Expected /evidence-repair in detail, got: {apis_errs[0].detail}"
            )
        finally:
            shutil.rmtree(tmpdir)

    def test_missing_evidence_detail_includes_evidence_repair_hint(self):
        """Missing evidence block detail references /evidence-repair."""
        tmpdir, p = _blog_file(_BLOG_MISSING_EVIDENCE)
        try:
            errors = check_file(p)
            ev_errs = [e for e in errors if e.check == "blog_evidence" and "missing" in e.detail]
            assert ev_errs, "Expected a blog_evidence error about missing block"
            assert "/evidence-repair" in ev_errs[0].detail, (
                f"Expected /evidence-repair in detail, got: {ev_errs[0].detail}"
            )
        finally:
            shutil.rmtree(tmpdir)

    def test_manual_remediation_bypasses_claims_apis_check(self):
        """Files with content_origin: manual-remediation are exempt from claims/apis check."""
        tmpdir, p = _blog_file(_BLOG_MANUAL_REMEDIATION)
        try:
            errors = check_file(p)
            # Should have no blog_evidence errors about claims or apis
            claims_api_errs = [
                e for e in errors
                if e.check == "blog_evidence" and ("claims" in e.detail or "apis" in e.detail)
            ]
            assert claims_api_errs == [], (
                f"manual-remediation should bypass claims/apis check, got: {claims_api_errs}"
            )
        finally:
            shutil.rmtree(tmpdir)

    def test_locale_file_excluded_from_p03(self):
        """Locale translation files (index.ar.md, index.fr.md) are NOT checked for P-03."""
        tmpdir, p = _blog_file(_BLOG_EMPTY_CLAIMS, filename="index.ar.md")
        try:
            errors = check_file(p)
            blog_errs = [e for e in errors if e.check == "blog_evidence"]
            assert blog_errs == [], (
                f"Locale files should be excluded from P-03, got: {blog_errs}"
            )
        finally:
            shutil.rmtree(tmpdir)

    def test_non_blog_file_excluded_from_p03(self):
        """Files outside content/blog.aspose.org/ are NOT checked for P-03."""
        # Use a regular temp file (not under blog.aspose.org/)
        p = _tmp_md(_BLOG_EMPTY_CLAIMS)
        try:
            errors = check_file(p)
            blog_errs = [e for e in errors if e.check == "blog_evidence"]
            assert blog_errs == [], (
                f"Non-blog files should be excluded from P-03, got: {blog_errs}"
            )
        finally:
            p.unlink(missing_ok=True)
