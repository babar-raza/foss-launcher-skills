"""Behavioral tests for attach_evidence.py — CLI entry point and evidence.runner.

Covers:
  - CLI: --files with nonexistent path → SKIP logged, no crash, exit 0
  - CLI: --files with file outside known site paths → SKIP (cannot infer product)
  - attach_files(): evidence block written with required fields (mocked Knowledge)
  - attach_files(): idempotent — second call with same model_sha → "SKIP (current)"
  - attach_evidence(): audit FAILs prevent evidence attachment
"""
from __future__ import annotations

import subprocess
import sys
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest

_PIPELINE_DIR = Path(__file__).resolve().parent.parent
if str(_PIPELINE_DIR) not in sys.path:
    sys.path.insert(0, str(_PIPELINE_DIR))

_SCRIPT = str(_PIPELINE_DIR / "commands" / "healing" / "attach_evidence.py")
_REPO_ROOT = _PIPELINE_DIR.parent.parent


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _make_content_file(path: Path, with_frontmatter: bool = True) -> Path:
    """Write a minimal markdown file with optional frontmatter."""
    if with_frontmatter:
        path.write_text(
            "---\ntitle: Test Page\nweight: 10\n---\n\n# Test\n\nSome content.\n",
            encoding="utf-8",
        )
    else:
        path.write_text("# Test\n\nSome content.\n", encoding="utf-8")
    return path


class _FakeKnowledge:
    """Minimal duck-type substitute. No disk I/O required."""

    def __init__(self, repo_sha="abc12345", version="1.0.0", platform="python"):
        self.available = True
        self.repo_sha = repo_sha
        self.version = version
        self.platform = platform
        self.claim_ids = set()
        self.classes = {}

    def has_method(self, *_): return False
    def has_property(self, *_): return False
    def has_enum_member(self, *_): return False


# ---------------------------------------------------------------------------
# Section 1 — CLI smoke tests via subprocess
# ---------------------------------------------------------------------------

class TestCLISkipPaths:
    def test_nonexistent_file_does_not_crash(self, tmp_path):
        """CLI --files with a nonexistent path must exit 0 and log SKIP, not crash."""
        ghost = str(tmp_path / "ghost.md")
        result = subprocess.run(
            [sys.executable, _SCRIPT, "--files", ghost],
            cwd=str(_REPO_ROOT),
            capture_output=True,
            text=True,
        )
        assert result.returncode == 0, (
            f"attach_evidence.py crashed (exit {result.returncode}):\n{result.stderr}"
        )
        # Must log SKIP, not raise an exception
        assert "SKIP" in result.stderr or "not found" in result.stderr.lower(), (
            f"Expected SKIP in stderr, got:\n{result.stderr}"
        )

    def test_file_outside_site_paths_skipped(self, tmp_path):
        """CLI --files with a file at an unknown path must SKIP (cannot infer product)."""
        f = tmp_path / "random_place" / "page.md"
        f.parent.mkdir()
        _make_content_file(f)

        result = subprocess.run(
            [sys.executable, _SCRIPT, "--files", str(f)],
            cwd=str(_REPO_ROOT),
            capture_output=True,
            text=True,
        )
        assert result.returncode == 0
        assert "SKIP" in result.stderr, (
            f"Expected SKIP for unrecognised path, got:\n{result.stderr}"
        )

    def test_no_args_prints_usage(self):
        """Invoking with no args must print usage and exit non-zero."""
        result = subprocess.run(
            [sys.executable, _SCRIPT],
            cwd=str(_REPO_ROOT),
            capture_output=True,
            text=True,
        )
        assert result.returncode != 0
        # Docstring usage text should appear in stdout or stderr
        output = result.stdout + result.stderr
        assert "python" in output.lower() or "usage" in output.lower() or "--files" in output


# ---------------------------------------------------------------------------
# Section 2 — Unit tests for attach_files() with mocked dependencies
# ---------------------------------------------------------------------------

class TestAttachFilesUnit:
    """Tests for evidence.runner.attach_files() using mocked Knowledge and helpers."""

    def _run_attach_files(self, file_path, fake_knowledge, second_call=False):
        """Invoke attach_files with all heavyweight dependencies mocked.

        write_grade / compute_grade / EVALUATOR_LOGIC_VERSION are lazy local
        imports inside attach_evidence(), so they must be patched at their
        source modules, not at evidence.runner.
        """
        import evidence.runner as er
        # Ensure source modules are imported so patch targets exist
        import grade_writer  # noqa: F401
        import content_eval.models  # noqa: F401
        import content_eval  # noqa: F401

        with (
            patch.object(er, "infer_product", return_value=("cells", "python")),
            patch("evidence.runner.Knowledge", return_value=fake_knowledge),
            patch("evidence.runner.extract_tokens", return_value=[]),
            patch("evidence.runner.verify_tokens", return_value=[]),
            patch("evidence.runner._map_tokens_to_evidence", return_value=([], [])),
            patch("evidence.runner._detect_formats", return_value=[]),
            patch("evidence.runner._build_sections_evidence", return_value=[]),
            patch("grade_writer.write_grade"),
            patch("content_eval.models.compute_grade", return_value="B"),
            patch.object(content_eval, "EVALUATOR_LOGIC_VERSION", "v1"),
        ):
            counts = er.attach_files([file_path])
        return counts

    def test_evidence_block_written(self, tmp_path):
        """attach_files() must write evidence block to frontmatter."""
        f = _make_content_file(tmp_path / "page.md")
        fk = _FakeKnowledge(repo_sha="sha001")

        counts = self._run_attach_files(f, fk)

        assert counts.get("UPDATED") == 1, f"Expected UPDATED, got {counts}"
        text = f.read_text(encoding="utf-8")
        assert "evidence:" in text

    def test_evidence_block_has_required_fields(self, tmp_path):
        """Written evidence block must contain model_sha, model_version, claims, apis."""
        import yaml

        f = _make_content_file(tmp_path / "page.md")
        fk = _FakeKnowledge(repo_sha="sha002", version="2.0.0")

        self._run_attach_files(f, fk)

        text = f.read_text(encoding="utf-8")
        # Extract frontmatter
        fm_text = text.split("---")[1]
        fm = yaml.safe_load(fm_text)
        ev = fm.get("evidence", {})

        assert ev.get("model_sha") == "sha002", f"model_sha missing or wrong: {ev}"
        assert ev.get("model_version") == "2.0.0", f"model_version missing or wrong: {ev}"
        assert "claims" in ev, f"claims key missing: {ev}"
        assert "apis" in ev, f"apis key missing: {ev}"
        assert isinstance(ev["claims"], list)
        assert isinstance(ev["apis"], list)

    def test_idempotent_same_sha(self, tmp_path):
        """Second call with same model_sha must return 'SKIP (current)', not 'UPDATED'."""
        f = _make_content_file(tmp_path / "page.md")
        fk = _FakeKnowledge(repo_sha="sha003")

        counts_first = self._run_attach_files(f, fk)
        assert counts_first.get("UPDATED") == 1, f"First call should be UPDATED: {counts_first}"

        counts_second = self._run_attach_files(f, fk)
        assert counts_second.get("SKIP (current)") == 1, (
            f"Second call with same sha should be SKIP (current): {counts_second}"
        )

    def test_file_without_frontmatter_gets_evidence_block(self, tmp_path):
        """Files with no frontmatter must receive a new frontmatter block with evidence."""
        f = _make_content_file(tmp_path / "nofm.md", with_frontmatter=False)
        fk = _FakeKnowledge(repo_sha="sha004")

        counts = self._run_attach_files(f, fk)

        assert counts.get("UPDATED") == 1
        text = f.read_text(encoding="utf-8")
        assert text.startswith("---")
        assert "evidence:" in text


# ---------------------------------------------------------------------------
# Section 3 — Audit FAIL gate
# ---------------------------------------------------------------------------

class TestAuditFailGate:
    def test_audit_fail_prevents_evidence(self, tmp_path):
        """Pages with audit FAIL findings must be skipped; evidence must NOT be written."""
        from unittest.mock import MagicMock
        import evidence.runner as er

        f = _make_content_file(tmp_path / "page.md")
        fk = _FakeKnowledge(repo_sha="sha005")

        # Simulate a FAIL finding
        fake_fail = MagicMock()
        fake_fail.level = "FAIL"

        with (
            patch.object(er, "infer_product", return_value=("cells", "python")),
            patch("evidence.runner.Knowledge", return_value=fk),
            patch("evidence.runner.extract_tokens", return_value=[]),
            patch("evidence.runner.verify_tokens", return_value=[fake_fail]),
            patch("evidence.runner._map_tokens_to_evidence", return_value=([], [])),
            patch("evidence.runner._detect_formats", return_value=[]),
            patch("evidence.runner._build_sections_evidence", return_value=[]),
        ):
            counts = er.attach_files([f])

        assert counts.get("SKIP (audit FAILs)") == 1, f"Expected SKIP (audit FAILs): {counts}"
        text = f.read_text(encoding="utf-8")
        assert "evidence:" not in text, "Evidence block must NOT be written when FAILs present"
