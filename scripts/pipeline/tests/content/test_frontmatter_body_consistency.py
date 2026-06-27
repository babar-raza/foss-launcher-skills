"""
Tests for scripts/pipeline/commands/content/frontmatter_body_consistency.py (S-108).

Min required: 6 tests. This file has 7.
"""

import pytest
from pathlib import Path

import commands.content.frontmatter_body_consistency as fbc


# ── Fixtures ──────────────────────────────────────────────────────────────

@pytest.fixture(autouse=True)
def reset_config():
    yield
    fbc.configure(content_root="content")


def _make_page(tmp_path: Path, filename: str, content: str) -> Path:
    p = tmp_path / filename
    p.write_text(content, encoding="utf-8")
    return p


# ── Tests ─────────────────────────────────────────────────────────────────

def test_consistent_page_passes(tmp_path):
    """Page where frontmatter and body are consistent produces verdict PASS."""
    page = _make_page(tmp_path, "page.md", """---
title: Test
evidence:
  formats:
    - format: PDF
---

## Overview

Aspose.PDF supports the PDF format natively.
""")
    result = fbc.check_page(str(page))
    assert result["verdict"] == "PASS"
    assert result["findings"] == []


def test_format_claim_contradiction_detected(tmp_path):
    """Body denying a frontmatter-listed format produces FORMAT_CLAIM_CONTRADICTION."""
    page = _make_page(tmp_path, "page.md", """---
title: Test
evidence:
  formats:
    - format: PDF
---

PDF is not supported by this product.
""")
    result = fbc.check_page(str(page))
    assert result["verdict"] == "FAIL"
    assert any(f["finding_type"] == fbc.FINDING_FORMAT_CONTRADICTION for f in result["findings"])


def test_package_name_mismatch_detected(tmp_path):
    """Frontmatter package name absent from body install commands produces finding."""
    page = _make_page(tmp_path, "page.md", """---
title: Test
install_info:
  package_name: Aspose.PDF
---

## Installation

Install using the NuGet manager.
""")
    result = fbc.check_page(str(page))
    # Aspose.PDF not mentioned in body — finding expected
    assert any(f["finding_type"] == fbc.FINDING_PACKAGE_MISMATCH for f in result["findings"])


def test_removed_api_in_body_detected(tmp_path):
    """API listed in evidence.removed_apis but found in body produces finding."""
    page = _make_page(tmp_path, "page.md", """---
title: Test
evidence:
  removed_apis:
    - LegacyConverter
---

Use LegacyConverter to convert documents.
""")
    result = fbc.check_page(str(page))
    assert result["verdict"] == "FAIL"
    assert any(f["finding_type"] == fbc.FINDING_REMOVED_API_IN_BODY for f in result["findings"])


def test_version_mismatch_no_false_positive(tmp_path):
    """Version check is conservative — no finding when versions match or are absent."""
    page = _make_page(tmp_path, "page.md", """---
title: Test
provenance:
  version: "26.5.0"
---

## Overview

Requires .NET 6 or higher.
""")
    result = fbc.check_page(str(page))
    # Version check is conservative; no findings expected from this
    version_findings = [f for f in result["findings"] if f["finding_type"] == fbc.FINDING_VERSION_MISMATCH]
    assert version_findings == []


def test_empty_frontmatter_passes(tmp_path):
    """Page with no frontmatter evidence fields produces verdict PASS."""
    page = _make_page(tmp_path, "page.md", """---
title: Test
---

Just some body content with no API references.
""")
    result = fbc.check_page(str(page))
    assert result["verdict"] == "PASS"


def test_multiple_findings_all_reported(tmp_path):
    """Multiple inconsistencies in the same page are all reported."""
    page = _make_page(tmp_path, "page.md", """---
title: Test
evidence:
  formats:
    - format: PDF
    - format: DOCX
  removed_apis:
    - OldClass
install_info:
  package_name: Aspose.PDF
---

PDF is not supported by this product.
Also DOCX is not supported.
OldClass is still referenced here.
""")
    result = fbc.check_page(str(page))
    assert result["verdict"] == "FAIL"
    finding_types = {f["finding_type"] for f in result["findings"]}
    assert fbc.FINDING_FORMAT_CONTRADICTION in finding_types
    assert fbc.FINDING_REMOVED_API_IN_BODY in finding_types
