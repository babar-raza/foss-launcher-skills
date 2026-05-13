"""Tests for launch_gate.py — L-08 gate and _check_provenance_coverage helper.

Coverage (Phase P / A-01):
  _check_provenance_coverage() — 6 input cases
  gate_l08_provenance_coverage() — 4 outcome scenarios
  _ALL_GATES — gate registry smoke test (D-01)
"""
from __future__ import annotations

import textwrap
from pathlib import Path

import pytest

from launch_gate import (
    STATUS_FAIL,
    STATUS_PASS,
    STATUS_SKIP,
    _ALL_GATES,
    _check_provenance_coverage,
    gate_l08_provenance_coverage,
    gate_l09_hugo_build,
    gate_l10_no_coming_soon,
    gate_l11_family_display_name,
)

import launch_gate as _lg_mod


@pytest.fixture(autouse=True)
def _reset_launch_gate():
    yield
    _lg_mod.configure()


# ---------------------------------------------------------------------------
# Tests for _check_provenance_coverage(text)
# ---------------------------------------------------------------------------

class TestCheckProvenanceCoverage:
    """Unit tests for the provenance-coverage text parser."""

    def test_no_frontmatter_opener_returns_ok(self):
        """File without leading --- has no frontmatter — always ok."""
        text = "title: Example\ncontent goes here\n"
        assert _check_provenance_coverage(text) == "ok"

    def test_structural_page_without_provenance_returns_ok(self):
        """Structural pages (layout: list/family/reference-home) are exempt from provenance requirement."""
        text = textwrap.dedent("""\
            ---
            title: Example
            layout: list
            ---
            Content here.
        """)
        assert _check_provenance_coverage(text) == "ok"

    def test_non_structural_without_provenance_returns_absent(self):
        """Non-structural content page with no provenance block returns absent_provenance (L-08b)."""
        text = textwrap.dedent("""\
            ---
            title: Example
            layout: reference-single
            ---
            Content here.
        """)
        assert _check_provenance_coverage(text) == "absent_provenance"

    def test_provenance_with_content_origin_returns_ok(self):
        """Provenance block with content_origin present — passes."""
        text = textwrap.dedent("""\
            ---
            title: Example
            provenance:
              content_origin: skill-generated
              last_mechanism: skill
              auto_updatable: true
            ---
            Content here.
        """)
        assert _check_provenance_coverage(text) == "ok"

    def test_provenance_without_content_origin_returns_missing(self):
        """Provenance block present but content_origin absent — Control 1 gap."""
        text = textwrap.dedent("""\
            ---
            title: Example
            provenance:
              last_mechanism: skill
              auto_updatable: true
            ---
            Content here.
        """)
        assert _check_provenance_coverage(text) == "missing_origin"

    def test_structural_deferred_returns_ok(self):
        """Structural-deferred pages (content_origin: unknown + provenance_recovery_note)
        are intentionally deferred and must NOT be flagged as missing_origin."""
        text = textwrap.dedent("""\
            ---
            title: Index Page
            provenance:
              content_origin: unknown
              last_mechanism: unknown
              auto_updatable: false
              provenance_recovery_note: structural-page
            ---
            Content here.
        """)
        assert _check_provenance_coverage(text) == "ok"

    def test_unclosed_frontmatter_returns_ok(self):
        """Frontmatter with no closing --- fails safe — no exception, returns ok."""
        text = "---\ntitle: Example\nprovenance:\n  last_mechanism: skill\n"
        assert _check_provenance_coverage(text) == "ok"


# ---------------------------------------------------------------------------
# Tests for gate_l08_provenance_coverage(family, platform)
# ---------------------------------------------------------------------------

class TestGateL08ProvenanceCoverage:
    """Integration-level tests using tmp_path for real file I/O."""

    def _content_root(self, tmp_path: Path, site: str, family: str, platform: str) -> Path:
        """Create and return content/<site>/en/<family>/<platform>/."""
        d = tmp_path / "content" / site / "en" / family / platform
        d.mkdir(parents=True)
        return d

    def test_no_matching_files_returns_skip(self, tmp_path, monkeypatch):
        """When glob finds no .md files the gate should SKIP, not FAIL."""
        import launch_gate as lg
        lg.configure(repo_root=tmp_path)
        result = gate_l08_provenance_coverage("nonexistent", "platform")
        assert result.status == STATUS_SKIP
        assert "no content files found" in result.detail

    def test_all_files_have_content_origin_returns_pass(self, tmp_path, monkeypatch):
        """All files correctly provisioned → PASS."""
        import launch_gate as lg
        lg.configure(repo_root=tmp_path)

        d = self._content_root(tmp_path, "docs.aspose.org", "widgets", "net")
        (d / "page.md").write_text(
            "---\ntitle: T\nprovenance:\n  content_origin: skill-generated\n---\n",
            encoding="utf-8",
        )

        result = gate_l08_provenance_coverage("widgets", "net")
        assert result.status == STATUS_PASS
        assert "all" in result.detail

    def test_file_missing_content_origin_returns_fail(self, tmp_path, monkeypatch):
        """One file with provenance block but no content_origin → FAIL."""
        import launch_gate as lg
        lg.configure(repo_root=tmp_path)

        d = self._content_root(tmp_path, "docs.aspose.org", "widgets", "net")
        (d / "good.md").write_text(
            "---\ntitle: Good\nprovenance:\n  content_origin: skill-generated\n---\n",
            encoding="utf-8",
        )
        (d / "bad.md").write_text(
            "---\ntitle: Bad\nprovenance:\n  last_mechanism: skill\n---\n",
            encoding="utf-8",
        )

        result = gate_l08_provenance_coverage("widgets", "net")
        assert result.status == STATUS_FAIL
        assert "1/2" in result.detail
        assert any("bad.md" in line for line in result.extra_lines)

    def test_structural_deferred_files_only_returns_pass(self, tmp_path, monkeypatch):
        """All files are structural-deferred (content_origin: unknown + note) → PASS.
        The gate must not flag intentionally deferred index pages."""
        import launch_gate as lg
        lg.configure(repo_root=tmp_path)

        d = self._content_root(tmp_path, "docs.aspose.org", "widgets", "net")
        (d / "_index.md").write_text(
            textwrap.dedent("""\
                ---
                title: Index
                provenance:
                  content_origin: unknown
                  last_mechanism: unknown
                  auto_updatable: false
                  provenance_recovery_note: structural-page
                ---
            """),
            encoding="utf-8",
        )

        result = gate_l08_provenance_coverage("widgets", "net")
        assert result.status == STATUS_PASS


# ---------------------------------------------------------------------------
# Smoke test: gate registry (D-01)
# ---------------------------------------------------------------------------

class TestGateRegistry:
    """Smoke test for the _ALL_GATES registry."""

    def test_gate_count_is_fifteen(self):
        """_ALL_GATES must contain exactly 15 entries.
        If this fails, a gate was added or removed without updating this test
        and the L-01-through-L-15 documentation."""
        assert len(_ALL_GATES) == 15, (
            f"Expected 15 gates, found {len(_ALL_GATES)}. "
            "Update this test and launch_gate.py docstring when adding/removing gates."
        )

    def test_l15_is_last_gate(self):
        """L-15 must be the last gate in the registry."""
        from launch_gate import gate_l15_snippet_syntax
        assert _ALL_GATES[-1] is gate_l15_snippet_syntax

    def test_l11_precedes_new_gates(self):
        """L-11 should precede L-12..L-15 in the registry."""
        assert _ALL_GATES[10] is gate_l11_family_display_name


# ---------------------------------------------------------------------------
# L-11 behavior tests
# ---------------------------------------------------------------------------

class TestL11FamilyDisplayName:
    """Behavior tests for gate_l11_family_display_name."""

    def test_pass_font(self):
        """L-11 passes for font (post-fix) across all 3 sites."""
        result = gate_l11_family_display_name("font", "python")
        assert result.status == STATUS_PASS
        assert "Aspose.Font FOSS" in result.detail

    def test_pass_cells(self):
        result = gate_l11_family_display_name("cells", "python")
        assert result.status == STATUS_PASS

    def test_pass_words(self):
        result = gate_l11_family_display_name("words", "python")
        assert result.status == STATUS_PASS

    def test_skip_unknown_family(self):
        """Family not in taxonomy should SKIP."""
        result = gate_l11_family_display_name("nonexistent_family_xyz", "python")
        assert result.status == STATUS_SKIP

    def test_skip_no_content(self):
        """Family in taxonomy but no content dirs should SKIP."""
        import tempfile
        import launch_gate as lg
        old_root = lg._CONTENT_ROOT
        try:
            lg._CONTENT_ROOT = Path(tempfile.mkdtemp())
            result = gate_l11_family_display_name("font", "python")
            assert result.status == STATUS_SKIP
        finally:
            lg._CONTENT_ROOT = old_root
