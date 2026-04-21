"""Tests for scripts/pipeline/no_downgrade_guard.py — pre-write quality guard."""
import json
import subprocess
import sys
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest

REPO_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(REPO_ROOT / "scripts" / "pipeline"))

from no_downgrade_guard import (
    DECISION_ALLOW,
    DECISION_BLOCK,
    DECISION_WARN,
    _decision,
    _extract_frontmatter_yaml,
    _fallback_grade_from_audit,
    _structural_check,
)


# ---------------------------------------------------------------------------
# _decision — grade comparison matrix
# ---------------------------------------------------------------------------

class TestDecision:
    def test_new_file_always_allow(self):
        assert _decision(None, "A", target_exists=False) == DECISION_ALLOW
        assert _decision(None, "F", target_exists=False) == DECISION_ALLOW

    def test_no_existing_grade_allow(self):
        assert _decision(None, "C", target_exists=True) == DECISION_ALLOW

    def test_low_existing_grade_allows_anything(self):
        assert _decision("D", "F", target_exists=True) == DECISION_ALLOW
        assert _decision("F", "F", target_exists=True) == DECISION_ALLOW
        assert _decision("D", "A", target_exists=True) == DECISION_ALLOW

    def test_existing_c_blocks_on_d_or_f(self):
        assert _decision("C", "D", target_exists=True) == DECISION_BLOCK
        assert _decision("C", "F", target_exists=True) == DECISION_BLOCK

    def test_existing_c_allows_on_c_or_better(self):
        assert _decision("C", "C", target_exists=True) == DECISION_ALLOW
        assert _decision("C", "B", target_exists=True) == DECISION_ALLOW
        assert _decision("C", "A", target_exists=True) == DECISION_ALLOW

    def test_existing_b_blocks_d_and_f(self):
        assert _decision("B", "D", target_exists=True) == DECISION_BLOCK
        assert _decision("B", "F", target_exists=True) == DECISION_BLOCK

    def test_existing_b_warns_on_c(self):
        assert _decision("B", "C", target_exists=True) == DECISION_WARN

    def test_existing_b_allows_b_or_a(self):
        assert _decision("B", "B", target_exists=True) == DECISION_ALLOW
        assert _decision("B", "A", target_exists=True) == DECISION_ALLOW

    def test_existing_a_blocks_d_and_f(self):
        assert _decision("A", "D", target_exists=True) == DECISION_BLOCK
        assert _decision("A", "F", target_exists=True) == DECISION_BLOCK

    def test_existing_a_warns_on_c(self):
        assert _decision("A", "C", target_exists=True) == DECISION_WARN

    def test_existing_a_allows_b_and_a(self):
        assert _decision("A", "B", target_exists=True) == DECISION_ALLOW
        assert _decision("A", "A", target_exists=True) == DECISION_ALLOW


# ---------------------------------------------------------------------------
# _structural_check — catastrophic regression detection
# ---------------------------------------------------------------------------

class TestStructuralCheck:
    def test_no_regression_returns_none(self):
        existing = "# Title\n\nSome content here.\n" * 5
        proposed = "# Title\n\nSome content here.\n" * 5
        assert _structural_check(existing, proposed) is None

    def test_word_count_collapse_blocks(self):
        existing = ("word " * 100) + "\n"
        proposed = ("word " * 10) + "\n"  # less than 30%
        result = _structural_check(existing, proposed)
        assert result is not None
        decision, reason = result
        assert decision == DECISION_BLOCK
        assert "word count" in reason

    def test_small_existing_word_count_not_blocked(self):
        """If existing has ≤50 words, word-count rule does not fire."""
        existing = "word " * 40 + "\n"
        proposed = "word " * 5 + "\n"
        assert _structural_check(existing, proposed) is None

    def test_heading_count_collapse_blocks(self):
        existing = "## H1\n\nbody\n\n## H2\n\nbody\n\n## H3\n\nbody\n## H4\n\nbody\n"
        proposed = "## H1\n\nbody\n"  # dropped from 4 to 1 heading (<50%)
        result = _structural_check(existing, proposed)
        assert result is not None
        decision, reason = result
        assert decision == DECISION_BLOCK
        assert "heading count" in reason

    def test_few_headings_not_blocked(self):
        """If existing has <3 headings, heading rule does not fire."""
        existing = "## H1\n\nbody\n\n## H2\n\nbody\n"
        proposed = "## H1\n\nbody\n"
        assert _structural_check(existing, proposed) is None

    def test_code_block_drop_warns(self):
        existing = "# Title\n\n```python\ncode1\n```\n\n```python\ncode2\n```\n"
        proposed = "# Title\n\nNo code here.\n"
        result = _structural_check(existing, proposed)
        assert result is not None
        decision, reason = result
        assert decision == DECISION_WARN
        assert "code blocks" in reason

    def test_no_code_blocks_in_existing_not_warned(self):
        """If existing has no code blocks (ex_code < 2), the rule does not fire."""
        existing = "# Title\n\nProse only, no code fences.\n"
        proposed = "# Title\n\nAlso prose only.\n"
        assert _structural_check(existing, proposed) is None

    def test_plugin_page_section_loss_blocks(self):
        """Removing enabled sections from plugin-layout frontmatter blocks."""
        existing = (
            "---\n"
            "layout: plugin\n"
            "hero:\n"
            "  enable: true\n"
            "features:\n"
            "  enable: true\n"
            "---\n\n# Body\n"
        )
        proposed = (
            "---\n"
            "layout: plugin\n"
            "hero:\n"
            "  enable: false\n"
            "features:\n"
            "  enable: true\n"
            "---\n\n# Body\n"
        )
        result = _structural_check(existing, proposed)
        assert result is not None
        decision, reason = result
        assert decision == DECISION_BLOCK
        assert "hero" in reason

    def test_plugin_page_all_sections_preserved_allows(self):
        existing = (
            "---\n"
            "layout: plugin\n"
            "hero:\n"
            "  enable: true\n"
            "---\n\n# Body\n"
        )
        proposed = (
            "---\n"
            "layout: plugin\n"
            "hero:\n"
            "  enable: true\n"
            "---\n\n# Updated body\n"
        )
        assert _structural_check(existing, proposed) is None


# ---------------------------------------------------------------------------
# _extract_frontmatter_yaml
# ---------------------------------------------------------------------------

class TestExtractFrontmatterYaml:
    def test_extracts_frontmatter(self):
        text = "---\ntitle: Hello\nlayout: plugin\n---\n\n# Body\n"
        result = _extract_frontmatter_yaml(text)
        assert result == "title: Hello\nlayout: plugin"

    def test_no_frontmatter_returns_none(self):
        text = "# No frontmatter here\n"
        assert _extract_frontmatter_yaml(text) is None

    def test_single_field_frontmatter(self):
        text = "---\ntitle: x\n---\n\n# Body\n"
        result = _extract_frontmatter_yaml(text)
        assert result == "title: x"


# ---------------------------------------------------------------------------
# compare_content — integration via force_regenerate shortcut
# ---------------------------------------------------------------------------

class TestCompareContent:
    """Light integration tests that bypass subprocess eval calls."""

    def test_force_regenerate_always_allow(self, tmp_path):
        """force_regenerate=True bypasses all checks and returns ALLOW."""
        from no_downgrade_guard import compare_content

        target = tmp_path / "page.md"
        target.write_text("# existing page\n\n" + "word " * 100, encoding="utf-8")
        proposed = "x"  # would normally be a huge structural regression

        result = compare_content(
            target,
            proposed_text=proposed,
            repo_root=tmp_path,
            force_regenerate=True,
        )
        assert result["decision"] == DECISION_ALLOW
        assert result["force_regenerate"] is True

    def test_new_file_no_target(self, tmp_path):
        """When target_path doesn't exist, structural check is skipped."""
        from no_downgrade_guard import compare_content

        target = tmp_path / "nonexistent.md"
        proposed = "# New page\n\nContent.\n"

        # Without eval subprocess actually running, this exercises the path
        # where target_exists=False and structural check is bypassed.
        # The result grade will be None (eval fails) → _decision returns ALLOW.
        result = compare_content(
            target,
            proposed_text=proposed,
            repo_root=tmp_path,
        )
        assert result["target_exists"] is False
        assert result["decision"] == DECISION_ALLOW

    def test_structural_regression_caught_before_eval(self, tmp_path):
        """Structural regression fires before subprocess eval is called."""
        from no_downgrade_guard import compare_content

        target = tmp_path / "page.md"
        # High word-count + 3 headings existing
        existing = (
            "## Section A\n\nword " * 30 + "\n"
            "## Section B\n\nword " * 30 + "\n"
            "## Section C\n\nword " * 30 + "\n"
        )
        target.write_text(existing, encoding="utf-8")
        proposed = "tiny"  # word count collapse

        result = compare_content(
            target,
            proposed_text=proposed,
            repo_root=tmp_path,
        )
        # Decision from structural check — grade fields are None
        assert result["decision"] == DECISION_BLOCK
        assert result["existing"]["grade"] is None
        assert result["proposed"]["grade"] is None


# ---------------------------------------------------------------------------
# _fallback_grade_from_audit — FAIL-count thresholds
# ---------------------------------------------------------------------------

class TestFallbackGradeFromAudit:
    """Test the FAIL-count → letter-grade mapping in _fallback_grade_from_audit."""

    def _mock_audit(self, fail_count: int, tmp_path: Path) -> str:
        """Patch subprocess.run to return output containing `fail_count` 'FAIL' strings."""
        fake_output = "FAIL\n" * fail_count
        mock_result = MagicMock()
        mock_result.stdout = fake_output
        mock_result.stderr = ""
        with patch("no_downgrade_guard.subprocess.run", return_value=mock_result):
            return _fallback_grade_from_audit(tmp_path / "page.md", tmp_path)

    def test_zero_fails_returns_b(self, tmp_path):
        assert self._mock_audit(0, tmp_path) == "B"

    def test_one_fail_returns_c(self, tmp_path):
        assert self._mock_audit(1, tmp_path) == "C"

    def test_two_fails_returns_c(self, tmp_path):
        assert self._mock_audit(2, tmp_path) == "C"

    def test_three_fails_returns_d(self, tmp_path):
        assert self._mock_audit(3, tmp_path) == "D"

    def test_five_fails_returns_d(self, tmp_path):
        assert self._mock_audit(5, tmp_path) == "D"

    def test_six_fails_returns_f(self, tmp_path):
        assert self._mock_audit(6, tmp_path) == "F"

    def test_many_fails_returns_f(self, tmp_path):
        assert self._mock_audit(20, tmp_path) == "F"

    def test_exception_returns_neutral_c(self, tmp_path):
        """When subprocess raises, returns 'C' as neutral fallback."""
        with patch("no_downgrade_guard.subprocess.run", side_effect=Exception("boom")):
            grade = _fallback_grade_from_audit(tmp_path / "page.md", tmp_path)
        assert grade == "C"


# ---------------------------------------------------------------------------
# main() CLI — exit codes and JSON output
# ---------------------------------------------------------------------------

class TestMainCli:
    """Test the CLI entry point via subprocess against the real script."""

    _SCRIPT = str(REPO_ROOT / "scripts" / "pipeline" / "no_downgrade_guard.py")

    def _run(self, args: list[str], proposed_text: str | None = None) -> subprocess.CompletedProcess:
        cmd = [sys.executable, self._SCRIPT] + args
        return subprocess.run(
            cmd,
            input=proposed_text,
            capture_output=True,
            text=True,
            timeout=30,
        )

    def test_new_file_target_exits_0(self, tmp_path):
        """ALLOW (new file) → exit 0."""
        proposed = tmp_path / "proposed.md"
        proposed.write_text("# New content\n\nsome body\n", encoding="utf-8")
        target = tmp_path / "nonexistent.md"  # does not exist

        result = self._run([str(target), "--proposed-file", str(proposed)])
        assert result.returncode == 0, f"stderr: {result.stderr}"

    def test_json_output_has_required_keys(self, tmp_path):
        """--json flag produces parseable JSON with required fields."""
        proposed = tmp_path / "proposed.md"
        proposed.write_text("# New content\n\nsome body\n", encoding="utf-8")
        target = tmp_path / "nonexistent.md"

        result = self._run([str(target), "--proposed-file", str(proposed), "--json"])
        assert result.returncode == 0

        data = json.loads(result.stdout)
        assert "decision" in data
        assert "reason" in data
        assert "target_exists" in data
        assert "existing" in data
        assert "proposed" in data

    def test_json_decision_allow_for_new_file(self, tmp_path):
        """New file → decision is ALLOW in JSON output."""
        proposed = tmp_path / "proposed.md"
        proposed.write_text("# page\n\nbody\n", encoding="utf-8")

        result = self._run(
            [str(tmp_path / "new.md"), "--proposed-file", str(proposed), "--json"]
        )
        data = json.loads(result.stdout)
        assert data["decision"] == DECISION_ALLOW
        assert data["target_exists"] is False

    def test_force_regenerate_exits_0(self, tmp_path):
        """--force-regenerate always exits 0 regardless of content quality."""
        # Create an existing target with lots of content
        target = tmp_path / "existing.md"
        target.write_text(
            "## A\n\nbody\n" * 20 + "```python\ncode\n```\n" * 5,
            encoding="utf-8",
        )
        proposed = tmp_path / "proposed.md"
        proposed.write_text("tiny", encoding="utf-8")

        result = self._run(
            [str(target), "--proposed-file", str(proposed), "--force-regenerate", "--json"]
        )
        assert result.returncode == 0
        data = json.loads(result.stdout)
        assert data["decision"] == DECISION_ALLOW
        assert data.get("force_regenerate") is True

    def test_structural_block_exits_2(self, tmp_path):
        """Structural regression → exit code 2 (BLOCK)."""
        target = tmp_path / "page.md"
        # Rich existing content that proposed will collapse
        target.write_text(
            "## Section A\n\n" + "word " * 60 + "\n"
            "## Section B\n\n" + "word " * 60 + "\n"
            "## Section C\n\n" + "word " * 60 + "\n",
            encoding="utf-8",
        )
        proposed = tmp_path / "proposed.md"
        proposed.write_text("x", encoding="utf-8")

        result = self._run([str(target), "--proposed-file", str(proposed), "--json"])
        assert result.returncode == 2
        data = json.loads(result.stdout)
        assert data["decision"] == DECISION_BLOCK

    def test_help_exits_0(self):
        """--help flag prints usage and exits 0."""
        result = self._run(["--help"])
        assert result.returncode == 0
        assert "no_downgrade_guard" in result.stdout or "usage" in result.stdout.lower()
