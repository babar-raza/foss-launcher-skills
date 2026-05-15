"""Tests for validate_plugin_structure.py — display-control severity promotion."""

import pytest
from pathlib import Path
from unittest.mock import patch

from validate_plugin_structure import check_file, Finding


def _write_plugin_page(tmp_path: Path, *, english: bool = True,
                       include_optional: bool = True,
                       include_more_formats: bool = True) -> Path:
    """Create a synthetic plugin page for testing."""
    locale = "en" if english else "fr"
    page_dir = tmp_path / "content" / "products.aspose.org" / locale / "test" / "python"
    page_dir.mkdir(parents=True, exist_ok=True)
    filepath = page_dir / "_index.md"

    sections = []
    sections.append("layout: plugin")
    sections.append('family_name: "Test FOSS"')
    sections.append('plugin_description: "Test desc"')
    sections.append('plugin_platform: "Python"')
    sections.append('head_title: "Test"')
    sections.append('head_description: "Test desc"')
    sections.append('title: "Test"')
    sections.append('description: "Test"')
    sections.append('github_url: "https://github.com/test"')
    sections.append("submenu:\n  enable: true")
    sections.append("overview:\n  enable: true\n  title: Test\n  content: Test content")
    sections.append("content:\n  enable: true\n  block:\n  - title_left: Test")
    sections.append("single:\n  enable: true\n  block:\n  - title: Test")
    sections.append("provenance:\n  content_origin: skill-generated")
    sections.append("evidence:\n  model_sha: abc123")

    if include_optional:
        sections.append("supportandlearning:\n  enable: true")
        sections.append("back_to_top:\n  enable: true")
    if include_more_formats:
        sections.append("more_formats:\n  enable: true")

    content = "---\n" + "\n".join(sections) + "\n---\n"
    filepath.write_text(content, encoding="utf-8")
    return filepath


class TestDisplaySectionSeverity:
    """Verify display-control sections are ERROR for English, WARN for locale."""

    def test_english_missing_optional_is_error(self, tmp_path):
        filepath = _write_plugin_page(tmp_path, english=True,
                                      include_optional=False,
                                      include_more_formats=False)
        findings = check_file(filepath)
        errors = [f for f in findings if f.severity == "ERROR"]
        assert len(errors) == 3, f"Expected 3 ERRORs for missing display sections, got {len(errors)}"
        check_ids = {f.check_id for f in errors}
        assert "MISSING_DISPLAY" in check_ids

    def test_locale_missing_optional_is_warn(self, tmp_path):
        filepath = _write_plugin_page(tmp_path, english=False,
                                      include_optional=False,
                                      include_more_formats=False)
        findings = check_file(filepath)
        errors = [f for f in findings if f.severity == "ERROR"]
        warns = [f for f in findings if f.severity == "WARN"]
        assert len(errors) == 0, "Locale pages should not get ERROR for missing display sections"
        display_warns = [f for f in warns if f.check_id == "MISSING_DISPLAY"]
        assert len(display_warns) == 3

    def test_english_complete_page_passes(self, tmp_path):
        filepath = _write_plugin_page(tmp_path, english=True,
                                      include_optional=True,
                                      include_more_formats=True)
        findings = check_file(filepath)
        fatals = [f for f in findings if f.severity == "FATAL"]
        errors = [f for f in findings if f.severity == "ERROR"]
        assert len(fatals) == 0
        assert len(errors) == 0

    def test_more_formats_included_in_check(self, tmp_path):
        filepath = _write_plugin_page(tmp_path, english=True,
                                      include_optional=True,
                                      include_more_formats=False)
        findings = check_file(filepath)
        errors = [f for f in findings if f.severity == "ERROR"]
        assert len(errors) == 1
        assert "more_formats" in errors[0].message


class TestBodyLeakDetection:
    """Verify BODY_LEAK detection — the primary defect this validator targets."""

    def test_body_leak_is_fatal(self, tmp_path):
        """Content sections placed in body (after ---) must produce FATAL BODY_LEAK."""
        page_dir = tmp_path / "content" / "products.aspose.org" / "en" / "test" / "python"
        page_dir.mkdir(parents=True, exist_ok=True)
        filepath = page_dir / "_index.md"
        # Valid frontmatter but content sections leaked into body
        content = (
            "---\n"
            "layout: plugin\n"
            'family_name: "Test FOSS"\n'
            'plugin_description: "Test"\n'
            'plugin_platform: "Python"\n'
            'head_title: "Test"\n'
            'head_description: "Test"\n'
            'title: "Test"\n'
            'description: "Test"\n'
            'github_url: "https://github.com/test"\n'
            "submenu:\n  enable: true\n"
            "overview:\n  enable: true\n  title: T\n  content: T\n"
            "content:\n  enable: true\n  block:\n  - title_left: T\n"
            "single:\n  enable: true\n  block:\n  - title: T\n"
            "provenance:\n  content_origin: skill-generated\n"
            "evidence:\n  model_sha: abc\n"
            "---\n"
            "overview:\n"
            "  This content was accidentally placed in the body\n"
        )
        filepath.write_text(content, encoding="utf-8")
        findings = check_file(filepath)
        fatals = [f for f in findings if f.severity == "FATAL" and f.check_id == "BODY_LEAK"]
        assert len(fatals) >= 1, (
            f"Expected FATAL BODY_LEAK for content leaked into body, "
            f"got: {[str(f) for f in findings]}"
        )

    def test_empty_body_no_leak(self, tmp_path):
        """An empty body should not trigger BODY_LEAK."""
        filepath = _write_plugin_page(tmp_path, english=True,
                                      include_optional=True,
                                      include_more_formats=True)
        findings = check_file(filepath)
        leak_findings = [f for f in findings if f.check_id == "BODY_LEAK"]
        assert len(leak_findings) == 0


class TestMissingRequiredKeys:
    """Verify MISSING_KEY detection for required frontmatter fields."""

    def test_missing_family_name_is_fatal(self, tmp_path):
        """Missing family_name must produce FATAL MISSING_KEY."""
        page_dir = tmp_path / "content" / "products.aspose.org" / "en" / "test" / "python"
        page_dir.mkdir(parents=True, exist_ok=True)
        filepath = page_dir / "_index.md"
        # Omit family_name
        content = (
            "---\n"
            "layout: plugin\n"
            'plugin_description: "Test"\n'
            'plugin_platform: "Python"\n'
            'head_title: "Test"\n'
            'head_description: "Test"\n'
            'title: "Test"\n'
            'description: "Test"\n'
            'github_url: "https://github.com/test"\n'
            "submenu:\n  enable: true\n"
            "overview:\n  enable: true\n  title: T\n  content: T\n"
            "content:\n  enable: true\n  block:\n  - title_left: T\n"
            "single:\n  enable: true\n  block:\n  - title: T\n"
            "supportandlearning:\n  enable: true\n"
            "more_formats:\n  enable: true\n"
            "back_to_top:\n  enable: true\n"
            "provenance:\n  content_origin: skill-generated\n"
            "evidence:\n  model_sha: abc\n"
            "---\n"
        )
        filepath.write_text(content, encoding="utf-8")
        findings = check_file(filepath)
        fatals = [f for f in findings if f.severity == "FATAL" and "family_name" in f.message]
        assert len(fatals) == 1, (
            f"Expected 1 FATAL for missing family_name, got: {[str(f) for f in fatals]}"
        )

    def test_missing_github_url_is_fatal(self, tmp_path):
        """Missing github_url must produce FATAL MISSING_KEY."""
        page_dir = tmp_path / "content" / "products.aspose.org" / "en" / "test" / "python"
        page_dir.mkdir(parents=True, exist_ok=True)
        filepath = page_dir / "_index.md"
        # Omit github_url
        content = (
            "---\n"
            "layout: plugin\n"
            'family_name: "Test FOSS"\n'
            'plugin_description: "Test"\n'
            'plugin_platform: "Python"\n'
            'head_title: "Test"\n'
            'head_description: "Test"\n'
            'title: "Test"\n'
            'description: "Test"\n'
            "submenu:\n  enable: true\n"
            "overview:\n  enable: true\n  title: T\n  content: T\n"
            "content:\n  enable: true\n  block:\n  - title_left: T\n"
            "single:\n  enable: true\n  block:\n  - title: T\n"
            "supportandlearning:\n  enable: true\n"
            "more_formats:\n  enable: true\n"
            "back_to_top:\n  enable: true\n"
            "provenance:\n  content_origin: skill-generated\n"
            "evidence:\n  model_sha: abc\n"
            "---\n"
        )
        filepath.write_text(content, encoding="utf-8")
        findings = check_file(filepath)
        fatals = [f for f in findings if f.severity == "FATAL" and "github_url" in f.message]
        assert len(fatals) == 1


class TestCodeBlockBlankLines:
    """Verify CODE_BLOCK_BLANK_LINES check detects fence boundary blank lines."""

    def _write_page_with_code(self, tmp_path: Path, content_value: str, english: bool = True) -> Path:
        """Create a plugin page with custom single.block[0].content value."""
        locale = "en" if english else "fr"
        page_dir = tmp_path / "content" / "products.aspose.org" / locale / "test" / "python"
        page_dir.mkdir(parents=True, exist_ok=True)
        filepath = page_dir / "_index.md"
        import yaml
        single_block = [{"title": "T", "content": content_value}]
        fm = {
            "layout": "plugin",
            "family_name": "Test FOSS",
            "plugin_description": "Test",
            "plugin_platform": "Python",
            "head_title": "Test",
            "head_description": "Test",
            "title": "Test",
            "description": "Test",
            "github_url": "https://github.com/test",
            "submenu": {"enable": True},
            "overview": {"enable": True, "title": "T", "content": "T"},
            "content": {"enable": True, "block": [{"title_left": "T"}]},
            "single": {"enable": True, "block": single_block},
            "supportandlearning": {"enable": True},
            "more_formats": {"enable": True},
            "back_to_top": {"enable": True},
            "provenance": {"content_origin": "skill-generated"},
            "evidence": {"model_sha": "abc123"},
        }
        text = "---\n" + yaml.dump(fm, allow_unicode=True, default_flow_style=False) + "---\n"
        filepath.write_text(text, encoding="utf-8")
        return filepath

    def test_blank_after_opening_fence_triggers_error(self, tmp_path):
        """Blank line immediately after opening code fence must produce CODE_BLOCK_BLANK_LINES ERROR."""
        filepath = self._write_page_with_code(
            tmp_path,
            "Intro.\n\n```python\n\nimport foo\nfoo.run()\n```\n",
        )
        findings = check_file(filepath)
        code_errors = [f for f in findings if f.check_id == "CODE_BLOCK_BLANK_LINES"]
        assert len(code_errors) >= 1, f"Expected CODE_BLOCK_BLANK_LINES, got: {[str(f) for f in findings]}"
        assert all(f.severity == "ERROR" for f in code_errors)

    def test_blank_before_closing_fence_triggers_error(self, tmp_path):
        """Blank line immediately before closing code fence must produce CODE_BLOCK_BLANK_LINES ERROR."""
        filepath = self._write_page_with_code(
            tmp_path,
            "Intro.\n\n```python\nimport foo\nfoo.run()\n\n```\n",
        )
        findings = check_file(filepath)
        code_errors = [f for f in findings if f.check_id == "CODE_BLOCK_BLANK_LINES"]
        assert len(code_errors) >= 1, f"Expected CODE_BLOCK_BLANK_LINES, got: {[str(f) for f in findings]}"
        assert all(f.severity == "ERROR" for f in code_errors)

    def test_internal_blank_in_short_snippet_triggers_error(self, tmp_path):
        """Internal blank line in a short snippet (<=8 code lines) must produce ERROR."""
        filepath = self._write_page_with_code(
            tmp_path,
            "Intro.\n\n```python\nimport foo\n\nfoo.run()\n```\n",
        )
        findings = check_file(filepath)
        code_errors = [f for f in findings if f.check_id == "CODE_BLOCK_BLANK_LINES"]
        assert len(code_errors) >= 1, f"Expected CODE_BLOCK_BLANK_LINES, got: {[str(f) for f in findings]}"
        assert all(f.severity == "ERROR" for f in code_errors)

    def test_clean_code_block_passes(self, tmp_path):
        """Code block with no blank lines at boundaries must not produce CODE_BLOCK_BLANK_LINES."""
        filepath = self._write_page_with_code(
            tmp_path,
            "Intro.\n\n```python\nimport foo\nfoo.run()\n```\n",
        )
        findings = check_file(filepath)
        code_errors = [f for f in findings if f.check_id == "CODE_BLOCK_BLANK_LINES"]
        assert len(code_errors) == 0, f"Unexpected CODE_BLOCK_BLANK_LINES: {[str(f) for f in code_errors]}"

    def test_blank_lines_in_prose_not_flagged(self, tmp_path):
        """Blank lines in prose text outside code fences must not produce CODE_BLOCK_BLANK_LINES."""
        filepath = self._write_page_with_code(
            tmp_path,
            "Intro.\n\nSome prose.\n\n```python\nimport foo\n```\n",
        )
        findings = check_file(filepath)
        code_errors = [f for f in findings if f.check_id == "CODE_BLOCK_BLANK_LINES"]
        assert len(code_errors) == 0, f"Prose blank lines must not be flagged: {[str(f) for f in code_errors]}"

    def test_locale_page_gets_warn_not_error(self, tmp_path):
        """Locale pages (non-English) with fence blank lines must produce WARN, not ERROR."""
        filepath = self._write_page_with_code(
            tmp_path,
            "Intro.\n\n```python\nimport foo\n\nfoo.run()\n```\n",
            english=False,
        )
        findings = check_file(filepath)
        code_warns = [f for f in findings if f.check_id == "CODE_BLOCK_BLANK_LINES" and f.severity == "WARN"]
        code_errors = [f for f in findings if f.check_id == "CODE_BLOCK_BLANK_LINES" and f.severity == "ERROR"]
        assert len(code_warns) >= 1, f"Expected WARN for locale page, got: {[str(f) for f in findings]}"
        assert len(code_errors) == 0, f"Locale page must not get ERROR: {[str(f) for f in code_errors]}"


class TestMissingEnable:
    """Verify MISSING_ENABLE for core sections without enable: true."""

    def test_overview_without_enable_is_error(self, tmp_path):
        """overview section present but missing enable: true -> ERROR."""
        page_dir = tmp_path / "content" / "products.aspose.org" / "en" / "test" / "python"
        page_dir.mkdir(parents=True, exist_ok=True)
        filepath = page_dir / "_index.md"
        content = (
            "---\n"
            "layout: plugin\n"
            'family_name: "Test FOSS"\n'
            'plugin_description: "Test"\n'
            'plugin_platform: "Python"\n'
            'head_title: "Test"\n'
            'head_description: "Test"\n'
            'title: "Test"\n'
            'description: "Test"\n'
            'github_url: "https://github.com/test"\n'
            "submenu:\n  enable: true\n"
            "overview:\n  title: T\n  content: T\n"  # missing enable: true
            "content:\n  enable: true\n  block:\n  - title_left: T\n"
            "single:\n  enable: true\n  block:\n  - title: T\n"
            "supportandlearning:\n  enable: true\n"
            "more_formats:\n  enable: true\n"
            "back_to_top:\n  enable: true\n"
            "provenance:\n  content_origin: skill-generated\n"
            "evidence:\n  model_sha: abc\n"
            "---\n"
        )
        filepath.write_text(content, encoding="utf-8")
        findings = check_file(filepath)
        enable_errors = [
            f for f in findings
            if f.severity == "ERROR" and f.check_id == "MISSING_ENABLE"
            and "overview" in f.message
        ]
        assert len(enable_errors) == 1
