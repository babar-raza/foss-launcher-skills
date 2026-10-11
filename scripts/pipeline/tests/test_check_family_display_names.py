"""Unit tests for check_family_display_names.py."""

from __future__ import annotations

import sys
import tempfile
from pathlib import Path

import pytest

_CI_CHECKS = Path(__file__).resolve().parent.parent.parent / "ci" / "checks"
if str(_CI_CHECKS) not in sys.path:
    sys.path.insert(0, str(_CI_CHECKS))

from check_family_display_names import _parse_frontmatter, check_file  # noqa: E402


def _tmp_md(content: str) -> Path:
    f = tempfile.NamedTemporaryFile(suffix=".md", mode="w", encoding="utf-8", delete=False)
    f.write(content)
    f.close()
    return Path(f.name)


TAXONOMY = {"font": "Aspose.Font", "cells": "Aspose.Cells", "words": "Aspose.Words"}


class TestParseFrontmatter:
    def test_valid(self):
        p = _tmp_md("---\ntitle: Hello\n---\nBody\n")
        fm, err = _parse_frontmatter(p)
        assert fm == {"title": "Hello"}
        assert err is None

    def test_missing_delimiters(self):
        p = _tmp_md("No frontmatter here\n")
        fm, err = _parse_frontmatter(p)
        assert fm is None
        assert "missing frontmatter" in err

    def test_unclosed(self):
        p = _tmp_md("---\ntitle: Hello\nNo closing\n")
        fm, err = _parse_frontmatter(p)
        assert fm is None
        assert "unclosed" in err

    def test_malformed_yaml(self):
        p = _tmp_md("---\n: : :\n  bad:\n---\n")
        fm, err = _parse_frontmatter(p)
        # yaml.safe_load may parse or fail depending on content
        # At minimum, check no crash
        assert fm is None or isinstance(fm, dict)

    def test_non_dict(self):
        p = _tmp_md("---\n- item1\n- item2\n---\n")
        fm, err = _parse_frontmatter(p)
        assert fm is None
        assert "expected dict" in err


class TestCheckFile:
    def test_pass_canonical(self):
        p = _tmp_md("---\ntitle: Aspose.Font FOSS\nsubtitle: Font loading and conversion\n---\nBody\n")
        violations = check_file(p, "font", TAXONOMY)
        assert violations == []

    def test_fail_linktitle_present(self):
        p = _tmp_md("---\ntitle: Aspose.Font FOSS\nsubtitle: Font loading and conversion\nlinkTitle: Font\n---\nBody\n")
        violations = check_file(p, "font", TAXONOMY)
        assert len(violations) == 1
        assert "V-01" in violations[0]
        assert "linkTitle" in violations[0]

    def test_fail_title_mismatch(self):
        p = _tmp_md("---\ntitle: Font Library\nsubtitle: Font loading and conversion\n---\nBody\n")
        violations = check_file(p, "font", TAXONOMY)
        assert len(violations) == 1
        assert "V-02" in violations[0]

    def test_fail_both(self):
        p = _tmp_md("---\ntitle: Font\nsubtitle: Font loading and conversion\nlinkTitle: Font\n---\nBody\n")
        violations = check_file(p, "font", TAXONOMY)
        assert len(violations) == 2

    def test_warn_not_in_taxonomy(self):
        p = _tmp_md("---\ntitle: Aspose.NewProduct FOSS\nsubtitle: Some product description\n---\nBody\n")
        violations = check_file(p, "newproduct", TAXONOMY)
        assert len(violations) == 1
        assert "WARN" in violations[0]

    def test_fail_unparsable(self):
        p = _tmp_md("No frontmatter\n")
        violations = check_file(p, "font", TAXONOMY)
        assert len(violations) == 1
        assert "V-00" in violations[0]
        assert "unparsable" in violations[0]

    def test_pass_cells(self):
        p = _tmp_md("---\ntitle: Aspose.Cells FOSS\nsubtitle: Spreadsheet processing\n---\nBody\n")
        violations = check_file(p, "cells", TAXONOMY)
        assert violations == []

    def test_pass_words(self):
        p = _tmp_md("---\ntitle: Aspose.Words FOSS\nsubtitle: Word document processing\n---\nBody\n")
        violations = check_file(p, "words", TAXONOMY)
        assert violations == []


class TestV03Subtitle:
    def test_subtitle_missing(self):
        p = _tmp_md("---\ntitle: Aspose.Font FOSS\n---\nBody\n")
        violations = check_file(p, "font", TAXONOMY)
        assert len(violations) == 1
        assert "V-03" in violations[0]
        assert "missing" in violations[0]

    def test_subtitle_empty_string(self):
        p = _tmp_md("---\ntitle: Aspose.Font FOSS\nsubtitle: \"\"\n---\nBody\n")
        violations = check_file(p, "font", TAXONOMY)
        assert len(violations) == 1
        assert "V-03" in violations[0]
        assert "empty" in violations[0]

    def test_subtitle_valid(self):
        p = _tmp_md("---\ntitle: Aspose.Font FOSS\nsubtitle: Font loading, rendering, and conversion\n---\nBody\n")
        violations = check_file(p, "font", TAXONOMY)
        assert violations == []

    def test_subtitle_exactly_55(self):
        sub = "A" * 55
        p = _tmp_md(f"---\ntitle: Aspose.Font FOSS\nsubtitle: {sub}\n---\nBody\n")
        violations = check_file(p, "font", TAXONOMY)
        assert violations == []

    def test_subtitle_over_55(self):
        sub = "A" * 60
        p = _tmp_md(f"---\ntitle: Aspose.Font FOSS\nsubtitle: {sub}\n---\nBody\n")
        violations = check_file(p, "font", TAXONOMY)
        assert len(violations) == 1
        assert "V-03" in violations[0]
        assert "hard max" in violations[0]

    def test_subtitle_whitespace_only(self):
        p = _tmp_md("---\ntitle: Aspose.Font FOSS\nsubtitle: \"   \"\n---\nBody\n")
        violations = check_file(p, "font", TAXONOMY)
        assert len(violations) == 1
        assert "V-03" in violations[0]
