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

from scripts.pipeline.launch_gate import (
    STATUS_FAIL,
    STATUS_PASS,
    STATUS_SKIP,
    _ALL_GATES,
    _check_provenance_coverage,
    gate_l08_provenance_coverage,
)


# ---------------------------------------------------------------------------
# Tests for _check_provenance_coverage(text)
# ---------------------------------------------------------------------------

class TestCheckProvenanceCoverage:
    """Unit tests for the provenance-coverage text parser."""

    def test_no_frontmatter_opener_returns_ok(self):
        """File without leading --- has no frontmatter — always ok."""
        text = "title: Example\ncontent goes here\n"
        assert _check_provenance_coverage(text) == "ok"

    def test_frontmatter_without_provenance_block_returns_ok(self):
        """Frontmatter that has no provenance: key is fine — no enforcement applies."""
        text = textwrap.dedent("""\
            ---
            title: Example
            layout: single
            ---
            Content here.
        """)
        assert _check_provenance_coverage(text) == "ok"

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
        import scripts.pipeline.launch_gate as lg
        monkeypatch.setattr(lg, "_REPO_ROOT", tmp_path)
        result = gate_l08_provenance_coverage("nonexistent", "platform")
        assert result.status == STATUS_SKIP
        assert "no content files found" in result.detail

    def test_all_files_have_content_origin_returns_pass(self, tmp_path, monkeypatch):
        """All files correctly provisioned → PASS."""
        import scripts.pipeline.launch_gate as lg
        monkeypatch.setattr(lg, "_REPO_ROOT", tmp_path)

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
        import scripts.pipeline.launch_gate as lg
        monkeypatch.setattr(lg, "_REPO_ROOT", tmp_path)

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
        import scripts.pipeline.launch_gate as lg
        monkeypatch.setattr(lg, "_REPO_ROOT", tmp_path)

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

    def test_gate_count_is_eight(self):
        """_ALL_GATES must contain exactly 8 entries.
        If this fails, a gate was added or removed without updating this test
        and the L-01-through-L-08 documentation."""
        assert len(_ALL_GATES) == 8, (
            f"Expected 8 gates, found {len(_ALL_GATES)}. "
            "Update this test and launch_gate.py docstring when adding/removing gates."
        )

    def test_l08_is_last_gate(self):
        """L-08 must be the last gate in the registry (ordered by gate number)."""
        assert _ALL_GATES[-1] is gate_l08_provenance_coverage
