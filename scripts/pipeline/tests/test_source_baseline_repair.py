"""Tests for SOURCE_BASELINE_MISSING repair (V7 final closure).

Validates:
1. previous_repo_sha is preserved on refresh
2. clone_cache uses --depth=2
3. All-zero SHA returns SOURCE_BASELINE_MISSING
4. Transition from zero to valid SHA
"""
from __future__ import annotations

import json
import sys
from pathlib import Path
import pytest

_PIPELINE_DIR = Path(__file__).resolve().parents[1]
if str(_PIPELINE_DIR) not in sys.path:
    sys.path.insert(0, str(_PIPELINE_DIR))

from commands.ops.semantic_source_classifier import classify, configure


# ---------------------------------------------------------------------------
# Test 1: previous_repo_sha preserved on refresh
# ---------------------------------------------------------------------------

class TestPreviousRepoShaPreserved:
    """Verify refresh_knowledge.py stores previous_repo_sha before overwrite."""

    def test_previous_repo_sha_write_present_in_source(self):
        """The refresh_knowledge.py code contains the previous_repo_sha logic."""
        source_path = _PIPELINE_DIR / "commands" / "knowledge" / "refresh_knowledge.py"
        source = source_path.read_text(encoding="utf-8")
        assert "previous_repo_sha" in source
        assert '_write_model_field(family, platform, "previous_repo_sha", current)' in source

    def test_previous_repo_sha_guarded_by_current_check(self):
        """The write is guarded by 'if current:' to avoid writing None."""
        source_path = _PIPELINE_DIR / "commands" / "knowledge" / "refresh_knowledge.py"
        source = source_path.read_text(encoding="utf-8")
        # Find the block containing both if current: and previous_repo_sha
        idx = source.find("previous_repo_sha")
        assert idx > 0
        # The 'if current:' guard should appear within 500 chars before
        block = source[max(0, idx - 100):idx + 200]
        assert "if current:" in block


# ---------------------------------------------------------------------------
# Test 2: depth=2 clone parameter
# ---------------------------------------------------------------------------

class TestDepth2CloneParameter:
    """Verify clone_cache.py uses --depth=2 for both clone and fetch."""

    def test_ensure_clone_uses_depth_2(self):
        """ensure_clone() clones with --depth 2."""
        source_path = _PIPELINE_DIR / "core" / "clone_cache.py"
        source = source_path.read_text(encoding="utf-8")
        assert '"git", "clone", "--depth", "2"' in source

    def test_update_clone_fetches_depth_2(self):
        """update_clone() fetches with --depth=2."""
        source_path = _PIPELINE_DIR / "core" / "clone_cache.py"
        source = source_path.read_text(encoding="utf-8")
        assert '"git", "fetch", "--depth=2", "origin"' in source

    def test_no_depth_1_remains_in_code(self):
        """No --depth=1 or --depth 1 remains in executable code of clone_cache.py."""
        source_path = _PIPELINE_DIR / "core" / "clone_cache.py"
        lines = source_path.read_text(encoding="utf-8").splitlines()
        for line in lines:
            stripped = line.strip()
            if stripped.startswith("#") or stripped.startswith('"""') or stripped.startswith("``"):
                continue
            if "Uses ``git fetch" in line:
                continue
            assert '"--depth=1"' not in line, f"Found --depth=1 in code line: {line}"
            assert '"--depth", "1"' not in line, f"Found --depth 1 in code line: {line}"


# ---------------------------------------------------------------------------
# Test 3: all-zero SHA returns SOURCE_BASELINE_MISSING
# ---------------------------------------------------------------------------

class TestAllZeroShaSourceBaselineMissing:
    """Verify classifier returns SOURCE_BASELINE_MISSING for all-zero old_sha."""

    def test_all_zero_sha_impact(self, tmp_path):
        """All-zero old_sha -> source_change_impact = SOURCE_BASELINE_MISSING."""
        zero_sha = "0" * 40
        new_sha = "a" * 40

        result, exit_code = classify(
            "cells", "net",
            old_sha=zero_sha,
            new_sha=new_sha,
            clone_cache_override=str(tmp_path),
            out_path=tmp_path / "out.json",
            repo_root=tmp_path,
        )
        assert result["source_change_impact"] == "SOURCE_BASELINE_MISSING"
        assert result["diff_available"] is False

    def test_all_zero_sha_exit_code_2(self, tmp_path):
        """All-zero old_sha -> exit_code = 2."""
        zero_sha = "0" * 40
        new_sha = "b" * 40

        result, exit_code = classify(
            "words", "python",
            old_sha=zero_sha,
            new_sha=new_sha,
            clone_cache_override=str(tmp_path),
            out_path=tmp_path / "out.json",
            repo_root=tmp_path,
        )
        assert exit_code == 2

    def test_all_zero_sha_proof_message(self, tmp_path):
        """All-zero old_sha -> proof contains SOURCE_BASELINE_MISSING message."""
        zero_sha = "0" * 40
        new_sha = "c" * 40

        result, _ = classify(
            "cells", "net",
            old_sha=zero_sha,
            new_sha=new_sha,
            clone_cache_override=str(tmp_path),
            out_path=tmp_path / "out.json",
            repo_root=tmp_path,
        )
        assert any("SOURCE_BASELINE_MISSING" in p for p in result["proof"])

    def test_all_zero_sha_output_file_written(self, tmp_path):
        """JSON output is written even for SOURCE_BASELINE_MISSING."""
        zero_sha = "0" * 40
        new_sha = "d" * 40
        out_path = tmp_path / "delta.json"

        classify(
            "cells", "net",
            old_sha=zero_sha,
            new_sha=new_sha,
            clone_cache_override=str(tmp_path),
            out_path=out_path,
            repo_root=tmp_path,
        )
        assert out_path.is_file()
        data = json.loads(out_path.read_text(encoding="utf-8"))
        assert data["source_change_impact"] == "SOURCE_BASELINE_MISSING"


# ---------------------------------------------------------------------------
# Test 4: transition from zero to valid SHA
# ---------------------------------------------------------------------------

class TestTransitionFromZeroToValidSha:
    """After first refresh stores previous_repo_sha, second call should work."""

    def test_non_zero_sha_does_not_trigger_baseline_missing(self, tmp_path):
        """A real (non-zero) old_sha does NOT return SOURCE_BASELINE_MISSING."""
        old_sha = "a1b2c3d4e5f67890abcdef1234567890abcdef12"
        new_sha = "f" * 40

        result, exit_code = classify(
            "cells", "net",
            old_sha=old_sha,
            new_sha=new_sha,
            clone_cache_override=str(tmp_path / "nonexistent"),
            out_path=tmp_path / "out.json",
            repo_root=tmp_path,
        )
        assert result["source_change_impact"] != "SOURCE_BASELINE_MISSING"
        assert exit_code == 1

    def test_valid_sha_with_clone_attempts_diff(self, tmp_path):
        """With valid SHAs and clone present, classifier attempts git diff."""
        old_sha = "b" * 40
        new_sha = "c" * 40

        calls = []

        def _fake_diff(clone_path, old_sha, new_sha):
            calls.append((clone_path, old_sha, new_sha))
            return [], "unknown revision", True

        configure(git_diff_fn=_fake_diff)
        try:
            result, exit_code = classify(
                "cells", "net",
                old_sha=old_sha,
                new_sha=new_sha,
                clone_cache_override=str(tmp_path),
                out_path=tmp_path / "out.json",
                repo_root=tmp_path,
            )
        finally:
            configure()  # reset to production defaults

        assert len(calls) == 1
        assert result["source_change_impact"] == "UNKNOWN"
        assert exit_code == 2
