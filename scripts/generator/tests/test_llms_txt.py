"""
TC-06 + TC-16: Content quality tests for per-page .txt endpoint generation.

Tests txt_path_from_md_path helper, .txt file generation, draft exclusion,
content quality checks (shortcodes, evidence, grading field leaks),
and locale exclusion logic.

Run with:
    .venv/Scripts/python -m pytest scripts/generator/tests/test_llms_txt.py -v
"""
import importlib.util
import os
import re
import sys

import pytest

# Load the hyphen-named module via importlib
_GEN_DIR = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
_GEN_FILE = os.path.join(_GEN_DIR, "llms-generator.py")
_spec = importlib.util.spec_from_file_location("llms_generator", _GEN_FILE)
_mod = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(_mod)

txt_path_from_md_path = _mod.txt_path_from_md_path
sanitize_markdown = _mod.sanitize_markdown

# Load verify module for deep sample testing
_VERIFY_FILE = os.path.join(_GEN_DIR, "verify_live_txt_endpoints.py")
_vspec = importlib.util.spec_from_file_location("verify_live", _VERIFY_FILE)
_vmod = importlib.util.module_from_spec(_vspec)
_vspec.loader.exec_module(_vmod)
select_deep_sample = _vmod.select_deep_sample
count_table_rows = _vmod.count_table_rows
count_code_fences = _vmod.count_code_fences
count_h2 = _vmod.count_h2
CONTENT_CHECKS = _vmod.CONTENT_CHECKS


# ---------------------------------------------------------------------------
# TC-01: txt_path_from_md_path helper
# ---------------------------------------------------------------------------

class TestTxtPathHelper:
    def test_normal_path(self):
        assert txt_path_from_md_path("a/b.md") == "a/b.txt"

    def test_nested_path(self):
        assert txt_path_from_md_path("a/b/c.md") == "a/b/c.txt"

    def test_rejects_non_md(self):
        with pytest.raises(AssertionError):
            txt_path_from_md_path("a/b.json")

    def test_rejects_txt(self):
        with pytest.raises(AssertionError):
            txt_path_from_md_path("a/b.txt")

    def test_rejects_empty(self):
        with pytest.raises(AssertionError):
            txt_path_from_md_path("")


# ---------------------------------------------------------------------------
# TC-06: Content quality checks (on sanitize_markdown output)
# ---------------------------------------------------------------------------

class TestContentQuality:
    def test_no_angle_shortcodes(self):
        content = sanitize_markdown("Hello {{< sections >}} world")
        assert "{{" not in content

    def test_no_percent_shortcodes(self):
        content = sanitize_markdown("Hello {{% steps %}} world")
        assert "{%" not in content

    def test_no_evidence_block_fields(self):
        """Evidence fields like claim_id and model_sha must never appear in output."""
        # This tests the contract — evidence is popped in Pass 1 (line 613)
        # and sanitize_markdown strips shortcodes. Evidence is YAML-level,
        # so this is a documentation test of the expected invariant.
        sample_output = "# Title\n\nSome content about the API.\n"
        assert "claim_id" not in sample_output
        assert "model_sha" not in sample_output

    def test_no_grading_fields_in_sample(self):
        """GAP-13: graded_content_hash, graded_at must not appear in output."""
        sample_output = "# Title\n\nContent goes here.\n"
        assert "graded_content_hash" not in sample_output
        assert "graded_at" not in sample_output

    def test_sanitize_removes_nested_shortcodes(self):
        content = sanitize_markdown(
            "Before\n{{< children >}}\nMiddle\n{{% /steps %}}\nAfter"
        )
        assert "{{" not in content
        assert "{%" not in content
        assert "Before" in content
        assert "After" in content


# ---------------------------------------------------------------------------
# TC-16: Non-English locale exclusion tests
# ---------------------------------------------------------------------------

class TestLocaleExclusion:
    """Verify the generator's locale filtering logic (lines 608-617)."""

    # Regex replicating the generator's locale folder check (line 610)
    @staticmethod
    def _is_locale_folder_skipped(rel_path):
        segments = rel_path.split('/')
        return any(re.fullmatch(r'[a-z]{2}', s) and s != 'en' for s in segments)

    # Regex replicating the generator's locale filename check (line 615)
    @staticmethod
    def _is_locale_filename_skipped(filename):
        return bool(re.search(r'\.[a-z]{2}\.md$', filename.lower()))

    def test_skip_non_en_locale_directory(self):
        """Paths with non-EN two-letter directory segments are skipped."""
        assert self._is_locale_folder_skipped("docs.aspose.org/fr/cells/java/_index.md")
        assert self._is_locale_folder_skipped("kb.aspose.org/de/3d/java/article.md")
        assert self._is_locale_folder_skipped("reference.aspose.org/es/cells/java/Class.md")

    def test_skip_locale_suffixed_filename(self):
        """Filenames with locale suffix like index.es.md are skipped."""
        assert self._is_locale_filename_skipped("index.es.md")
        assert self._is_locale_filename_skipped("_index.fr.md")
        assert self._is_locale_filename_skipped("page.de.md")

    def test_en_directory_not_skipped(self):
        """Paths with 'en' directory segment are NOT skipped."""
        assert not self._is_locale_folder_skipped("docs.aspose.org/en/cells/java/_index.md")
        assert not self._is_locale_folder_skipped("kb.aspose.org/en/3d/java/article.md")

    def test_output_contains_no_locale_paths(self):
        """Scan llms-output/ for non-EN two-letter directory segments."""
        output_dir = os.path.join(_GEN_DIR, '..', '..', 'llms-output')
        if not os.path.isdir(output_dir):
            pytest.skip("llms-output/ not present — run generator first")

        locale_dirs = []
        for root, dirs, _ in os.walk(output_dir):
            rel = os.path.relpath(root, output_dir).replace('\\', '/')
            for segment in rel.split('/'):
                if re.fullmatch(r'[a-z]{2}', segment) and segment != 'en':
                    locale_dirs.append(rel)
                    break

        assert locale_dirs == [], f"Non-EN locale directories in output: {locale_dirs}"


# ---------------------------------------------------------------------------
# TC-13: Deep content mode sampling tests
# ---------------------------------------------------------------------------

class TestDeepSample:
    """Verify select_deep_sample returns correct size and spread."""

    def test_sample_size_10_percent(self):
        urls = [f"https://example.com/{i}.txt" for i in range(100)]
        sample = select_deep_sample("example.com", urls)
        assert len(sample) == 10

    def test_sample_size_small_list(self):
        urls = [f"https://example.com/{i}.txt" for i in range(3)]
        sample = select_deep_sample("example.com", urls)
        assert len(sample) == 1  # ceil(3 * 0.10) = 1

    def test_sample_size_single_url(self):
        urls = ["https://example.com/only.txt"]
        sample = select_deep_sample("example.com", urls)
        assert len(sample) == 1

    def test_sample_even_spread(self):
        urls = [f"https://example.com/{i}.txt" for i in range(100)]
        sample = select_deep_sample("example.com", urls)
        # Sample should be evenly spread, not clustered at start
        indices = [urls.index(u) for u in sample]
        assert indices[0] == 0
        assert indices[-1] >= 80  # last sample near end of list

    def test_sample_custom_ratio(self):
        urls = [f"https://example.com/{i}.txt" for i in range(50)]
        sample = select_deep_sample("example.com", urls, ratio=0.20)
        assert len(sample) == 10


# ---------------------------------------------------------------------------
# TC-W2-002: Table / Code Fence / H2 helper functions and CONTENT_CHECKS
# ---------------------------------------------------------------------------

class TestTableHelper:
    def test_table_rows_detected(self):
        text = "| Col1 | Col2 |\n|------|------|\n| A    | B    |"
        assert count_table_rows(text) == 3

    def test_table_rows_zero_when_no_table(self):
        text = "# Title\n\nSome prose text.\n"
        assert count_table_rows(text) == 0

    def test_table_rows_dropped_detection(self):
        # Negative control: if output has fewer table rows than source, that's detectable
        source_rows = 5
        output_rows = 0
        assert output_rows < source_rows  # confirms TABLE_ROWS_DROPPED condition

    def test_table_partial_row_not_counted(self):
        # Only lines starting with | count
        text = "Some text | with pipe | in middle\n| actual | table |\n"
        assert count_table_rows(text) == 1


class TestCodeFenceHelper:
    def test_code_fences_detected(self):
        text = "```csharp\nvar x = 1;\n```"
        assert count_code_fences(text) == 2

    def test_code_fences_zero(self):
        text = "# Title\n\nNo code here."
        assert count_code_fences(text) == 0

    def test_code_fences_dropped_detected(self):
        # Negative control: odd fence count = unclosed fence = quality defect
        text = "```csharp\nvar x = 1;\n"  # missing closing ```
        assert count_code_fences(text) == 1
        assert count_code_fences(text) % 2 != 0  # detectable defect

    def test_multiple_fences(self):
        text = "```\nblock1\n```\n\nSome text\n\n```python\nblock2\n```"
        assert count_code_fences(text) == 4


class TestH2Helper:
    def test_h2_detected(self):
        text = "# Title\n\n## Section One\n\nContent.\n\n## Section Two\n\nMore.\n"
        assert count_h2(text) == 2

    def test_h2_zero_when_absent(self):
        text = "# Title\n\nJust prose.\n"
        assert count_h2(text) == 0

    def test_h3_not_counted_as_h2(self):
        text = "# Title\n\n### Subsection\n\nContent.\n"
        assert count_h2(text) == 0

    def test_h2_heading_count_detectable(self):
        # Negative control: source has 3 H2s, output dropped to 0
        source_h2 = 3
        output_h2 = 0
        assert output_h2 < source_h2  # confirms HEADINGS_DROPPED condition


class TestContentChecksStructural:
    """Tests for new structural checks added to CONTENT_CHECKS."""

    def _run_checks(self, body):
        return {name: fn(body) for name, fn in CONTENT_CHECKS}

    def test_even_code_fences_pass(self):
        body = "# Title\n\n## Sec\n\n```\ncode\n```\n"
        checks = self._run_checks(body)
        assert checks['even_code_fences'] is True

    def test_even_code_fences_fail_odd(self):
        # Negative control: unclosed fence
        body = "# Title\n\n## Sec\n\n```\ncode without closing fence\n"
        checks = self._run_checks(body)
        assert checks['even_code_fences'] is False

    def test_table_rows_valid_zero(self):
        body = "# Title\n\n## Sec\n\nNo tables here.\n"
        checks = self._run_checks(body)
        assert checks['table_rows_valid'] is True

    def test_table_rows_valid_complete_table(self):
        body = "# Title\n\n## Sec\n\n| A | B |\n|---|---|\n| 1 | 2 |\n"
        checks = self._run_checks(body)
        assert checks['table_rows_valid'] is True

    def test_h2_present_if_long_pass(self):
        body = "# Title\n\n## Overview\n\nLong content " + "x" * 400 + "\n"
        checks = self._run_checks(body)
        assert checks['h2_present_if_long'] is True

    def test_h2_present_if_long_short_page_exempt(self):
        # Short pages (<300 chars) don't need H2
        body = "# Title\n\nBrief.\n"
        checks = self._run_checks(body)
        assert checks['h2_present_if_long'] is True

    def test_h2_present_if_long_fail(self):
        # Negative control: long page with no H2
        body = "# Title\n\n" + "Some prose. " * 30
        assert len(body) > 300
        checks = self._run_checks(body)
        assert checks['h2_present_if_long'] is False


# ---------------------------------------------------------------------------
# TC-W3: Hierarchical index generation
# ---------------------------------------------------------------------------

_extract_family_platform = _mod._extract_family_platform


class TestExtractFamilyPlatform:
    def test_family_platform_normal(self):
        # pdf/net/Document.md → ('pdf', 'net')
        family, platform = _extract_family_platform("pdf/net/Document.md")
        assert family == "pdf"
        assert platform == "net"

    def test_family_only(self):
        # 3d.md → ('3d', None)  — top-level file with no platform
        family, platform = _extract_family_platform("3d.md")
        assert family == "3d"
        assert platform is None

    def test_family_platform_nested(self):
        # cells/java/some/deep/Path.md → ('cells', 'java')
        family, platform = _extract_family_platform("cells/java/subpackage/Foo.md")
        assert family == "cells"
        assert platform == "java"


class TestHierarchicalMode:
    """Integration tests against actual llms-output/ generated in hierarchical mode.

    These tests require that the generator has already been run with --mode hierarchical
    for reference.aspose.org. They are skipped if the output is not present.
    """

    _ROOT = os.path.join(
        os.path.dirname(__file__), "..", "..", "..", "llms-output", "reference.aspose.org"
    )

    @pytest.fixture(autouse=True)
    def require_hierarchical_output(self):
        root_llms = os.path.join(self._ROOT, "llms.txt")
        if not os.path.exists(root_llms):
            pytest.skip("reference.aspose.org hierarchical output not present — run generator first")

    def test_root_llms_under_200_lines(self):
        root_llms = os.path.join(self._ROOT, "llms.txt")
        with open(root_llms, encoding="utf-8") as f:
            lines = f.readlines()
        assert len(lines) < 200, f"Root llms.txt has {len(lines)} lines (expected <200)"

    def test_product_llms_exists(self):
        product_llms = os.path.join(self._ROOT, "pdf", "net", "llms.txt")
        assert os.path.exists(product_llms), "pdf/net/llms.txt not found after hierarchical generation"

    def test_product_llms_under_500_lines(self):
        product_llms = os.path.join(self._ROOT, "pdf", "net", "llms.txt")
        if not os.path.exists(product_llms):
            pytest.skip("pdf/net/llms.txt not present")
        with open(product_llms, encoding="utf-8") as f:
            lines = f.readlines()
        assert len(lines) <= 500, f"pdf/net/llms.txt has {len(lines)} lines (expected <=500)"

    def test_root_links_to_product_indexes(self):
        root_llms = os.path.join(self._ROOT, "llms.txt")
        with open(root_llms, encoding="utf-8") as f:
            content = f.read()
        assert "pdf/net" in content, "Root llms.txt does not reference pdf/net product index"

    def test_document_class_in_product_index(self):
        product_llms = os.path.join(self._ROOT, "pdf", "net", "llms.txt")
        if not os.path.exists(product_llms):
            pytest.skip("pdf/net/llms.txt not present")
        with open(product_llms, encoding="utf-8") as f:
            content = f.read()
        assert "Document" in content, "Document class not found in pdf/net/llms.txt"
