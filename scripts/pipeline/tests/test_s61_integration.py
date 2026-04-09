"""Integration test for S-61 post-processing chain.

Exercises the deterministic portion of the /new-products-page skill:
  complete_plugin_structure -> validate_plugin_structure

Proves that a plugin page missing display-control sections is correctly
completed and passes structural validation with 0 FATAL and 0 ERROR.

Does NOT test LLM-generated content (Steps 1-10) or content_eval (Step 15)
because those are non-deterministic.  Does NOT test attach_evidence (Step 12)
because it requires knowledge artifacts.
"""
from __future__ import annotations

import textwrap
from pathlib import Path

import pytest

from complete_plugin_structure import complete_file
from validate_plugin_structure import check_file


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------

_MINIMAL_PLUGIN_PAGE = textwrap.dedent("""\
    ---
    layout: plugin
    family_name: "Test FOSS"
    plugin_description: "Open-source test library"
    plugin_platform: "Python"
    head_title: "Test FOSS for Python"
    head_description: "Open-source test library for Python"
    title: "Test FOSS for Python"
    description: "Open-source test library for Python"
    github_url: "https://github.com/test/test-foss"
    submenu:
      enable: true
    overview:
      enable: true
      title: "Test Library"
      content: |
        Test overview content paragraph.
    content:
      enable: true
      block:
      - title_left: "Feature A"
        content_left: |
          - Bullet one
        title_right: "Use Cases"
        content_right: |
          - Case one
    single:
      enable: true
      block:
      - title: "Example"
        content: |
          Example content
    provenance:
      content_origin: skill-generated
      last_mechanism: skill
      auto_updatable: true
    evidence:
      model_sha: "abc123"
      model_version: "1"
      claims: []
      apis: []
    ---
""")


def _write_page(tmp_path: Path, content: str, *, english: bool = True) -> Path:
    locale = "en" if english else "fr"
    page_dir = tmp_path / "content" / "products.aspose.org" / locale / "test" / "python"
    page_dir.mkdir(parents=True, exist_ok=True)
    filepath = page_dir / "_index.md"
    filepath.write_text(content, encoding="utf-8")
    return filepath


def _incomplete_page(include_display: bool = False) -> str:
    """Return a plugin page with or without display-control sections."""
    base = _MINIMAL_PLUGIN_PAGE
    if include_display:
        # Insert display sections before provenance (root-level YAML keys)
        display = (
            "supportandlearning:\n"
            "  enable: true\n"
            "more_formats:\n"
            "  enable: true\n"
            "back_to_top:\n"
            "  enable: true\n"
        )
        base = base.replace("provenance:\n", display + "provenance:\n")
    return base


# ---------------------------------------------------------------------------
# Tests
# ---------------------------------------------------------------------------

class TestS61IntegrationChain:
    """Integration: complete_plugin_structure -> validate_plugin_structure."""

    def test_incomplete_page_completes_then_validates(self, tmp_path):
        """A page missing display sections -> complete -> validate = 0 FATAL, 0 ERROR."""
        filepath = _write_page(tmp_path, _incomplete_page(include_display=False))

        # Pre-check: validator should find ERROR on English page missing display sections
        pre_findings = check_file(filepath)
        pre_errors = [f for f in pre_findings if f.severity == "ERROR"]
        assert len(pre_errors) == 3, (
            f"Expected 3 ERRORs for missing display sections before completion, "
            f"got {len(pre_errors)}"
        )

        # Step 11: complete_plugin_structure
        modified = complete_file(filepath)
        assert modified is True, "complete_file should have modified the incomplete page"

        # Step 13: validate_plugin_structure
        post_findings = check_file(filepath)
        post_fatals = [f for f in post_findings if f.severity == "FATAL"]
        post_errors = [f for f in post_findings if f.severity == "ERROR"]
        assert len(post_fatals) == 0, (
            f"Expected 0 FATAL after completion, got: "
            f"{[str(f) for f in post_fatals]}"
        )
        assert len(post_errors) == 0, (
            f"Expected 0 ERROR after completion, got: "
            f"{[str(f) for f in post_errors]}"
        )

    def test_complete_page_passes_without_modification(self, tmp_path):
        """A page with all sections -> complete (no-op) -> validate = clean."""
        filepath = _write_page(tmp_path, _incomplete_page(include_display=True))

        modified = complete_file(filepath)
        assert modified is False, "complete_file should not modify a complete page"

        findings = check_file(filepath)
        fatals = [f for f in findings if f.severity == "FATAL"]
        errors = [f for f in findings if f.severity == "ERROR"]
        assert len(fatals) == 0
        assert len(errors) == 0

    def test_chain_is_idempotent(self, tmp_path):
        """Running complete + validate twice produces identical results."""
        filepath = _write_page(tmp_path, _incomplete_page(include_display=False))

        # First pass
        complete_file(filepath)
        findings_1 = check_file(filepath)

        # Second pass
        modified_2 = complete_file(filepath)
        findings_2 = check_file(filepath)

        assert modified_2 is False, "Second complete_file run should be a no-op"
        assert len(findings_1) == len(findings_2)

    def test_locale_page_chain(self, tmp_path):
        """Locale page: complete + validate = 0 FATAL, 0 ERROR, 0 WARN for display."""
        filepath = _write_page(
            tmp_path, _incomplete_page(include_display=False), english=False
        )

        # Complete the page
        complete_file(filepath)

        # Validate
        findings = check_file(filepath)
        fatals = [f for f in findings if f.severity == "FATAL"]
        errors = [f for f in findings if f.severity == "ERROR"]
        display_warns = [
            f for f in findings
            if f.severity == "WARN" and f.check_id == "MISSING_DISPLAY"
        ]

        assert len(fatals) == 0
        assert len(errors) == 0
        assert len(display_warns) == 0, (
            "After completion, locale page should have no MISSING_DISPLAY warnings"
        )

    def test_body_content_preserved_after_completion(self, tmp_path):
        """Completion must not alter the page body (which should be empty)."""
        filepath = _write_page(tmp_path, _incomplete_page(include_display=False))

        complete_file(filepath)

        text = filepath.read_text(encoding="utf-8")
        # Body is everything after the closing ---
        parts = text.split("---")
        # parts[0] = empty (before opening ---), parts[1] = frontmatter, parts[2] = body
        assert len(parts) >= 3
        body = "---".join(parts[2:]).strip()
        assert body == "", f"Body should be empty after completion, got: {body!r}"
