"""Tests for gap-eval Stage 2 determinism and exhaustive default."""

from __future__ import annotations

import sys
from pathlib import Path
from unittest.mock import patch, MagicMock

import pytest

# Allow imports from scripts/gap-eval/
_GAP_EVAL_DIR = Path(__file__).resolve().parents[2] / "gap-eval" / "src"
if str(_GAP_EVAL_DIR) not in sys.path:
    sys.path.insert(0, str(_GAP_EVAL_DIR))

from run import stage2_knowledge_validation, _apply_false_positives, compute_verdict  # type: ignore  # noqa: E402


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _make_api_data(n: int) -> list[dict]:
    """Create n fake api_surface entries."""
    return [{"name": f"Class{i}", "type": "class"} for i in range(n)]


def _make_id_fn(family, platform, ftype, fpath, line, old_value):
    return f"F-{family}-{platform}-{ftype[:4]}-{old_value}"


def _mock_grep_not_found(*args, **kwargs):
    """Simulate grep finding nothing (returncode 1, no stdout)."""
    m = MagicMock()
    m.returncode = 1
    m.stdout = ""
    return m


def _mock_grep_found(*args, **kwargs):
    """Simulate grep finding the entry (returncode 0, some stdout)."""
    m = MagicMock()
    m.returncode = 0
    m.stdout = "/some/file.py\n"
    return m


# ---------------------------------------------------------------------------
# Tests
# ---------------------------------------------------------------------------

class TestStage2Determinism:
    """Verify Stage 2 exhaustive default and deterministic sampling."""

    def test_exhaustive_is_default(self, tmp_path):
        """With max_entries=0 (default), ALL api_surface entries are checked."""
        api_data = _make_api_data(20)
        checked_names: list[str] = []

        def _capture_grep(*args, **kwargs):
            # Extract the name being searched (4th-to-last arg before clone_path)
            cmd = args[0] if args else kwargs.get("args", [])
            # cmd format: ["grep", "-r", ..., "-l", name, str(clone_path)]
            name = cmd[-2]
            checked_names.append(name)
            return _mock_grep_found()

        # T3-MOCK: target=subprocess.run reason="grep clone-cache boundary call" removal=PERMANENT
        with patch("subprocess.run", side_effect=_capture_grep):
            stage2_knowledge_validation(
                "test", "python", tmp_path, api_data, _make_id_fn,
            )

        assert len(checked_names) == 20, (
            f"Expected all 20 entries checked, got {len(checked_names)}"
        )
        assert set(checked_names) == {f"Class{i}" for i in range(20)}

    def test_sampled_deterministic(self, tmp_path):
        """With max_entries>0 and fixed seed, two calls produce identical samples."""
        api_data = _make_api_data(50)

        def _run_and_collect():
            checked: list[str] = []

            def _capture(*args, **kwargs):
                cmd = args[0] if args else kwargs.get("args", [])
                checked.append(cmd[-2])
                return _mock_grep_found()

            # T3-MOCK: target=subprocess.run reason="grep clone-cache boundary call" removal=PERMANENT
            with patch("subprocess.run", side_effect=_capture):
                stage2_knowledge_validation(
                    "test", "python", tmp_path, api_data, _make_id_fn,
                    max_entries=10, seed=42,
                )
            return checked

        run1 = _run_and_collect()
        run2 = _run_and_collect()
        assert run1 == run2, "Same seed + same max_entries must produce identical samples"
        assert len(run1) == 10

    def test_different_seed_different_sample(self, tmp_path):
        """Different seeds produce different samples (proves seed is effective)."""
        api_data = _make_api_data(50)

        def _run_with_seed(seed):
            checked: list[str] = []

            def _capture(*args, **kwargs):
                cmd = args[0] if args else kwargs.get("args", [])
                checked.append(cmd[-2])
                return _mock_grep_found()

            # T3-MOCK: target=subprocess.run reason="grep clone-cache boundary call" removal=PERMANENT
            with patch("subprocess.run", side_effect=_capture):
                stage2_knowledge_validation(
                    "test", "python", tmp_path, api_data, _make_id_fn,
                    max_entries=10, seed=seed,
                )
            return checked

        sample_42 = _run_with_seed(42)
        sample_99 = _run_with_seed(99)
        assert sample_42 != sample_99, "Different seeds should produce different samples"

    def test_exhaustive_finds_all_phantoms(self, tmp_path):
        """Exhaustive mode catches phantom APIs that sampling would miss."""
        api_data = _make_api_data(20)
        # Make all entries "not found" in clone cache
        # T3-MOCK: target=subprocess.run reason="grep clone-cache boundary call" removal=PERMANENT
        with patch("subprocess.run", side_effect=_mock_grep_not_found):
            findings = stage2_knowledge_validation(
                "test", "python", tmp_path, api_data, _make_id_fn,
            )

        assert len(findings) == 20, (
            f"Exhaustive should flag all 20 phantom entries, got {len(findings)}"
        )

    def test_sampled_misses_phantoms(self, tmp_path):
        """Sampled mode only catches phantoms within the sample."""
        api_data = _make_api_data(50)
        # T3-MOCK: target=subprocess.run reason="grep clone-cache boundary call" removal=PERMANENT
        with patch("subprocess.run", side_effect=_mock_grep_not_found):
            findings = stage2_knowledge_validation(
                "test", "python", tmp_path, api_data, _make_id_fn,
                max_entries=10, seed=42,
            )

        assert len(findings) == 10, (
            f"Sample of 10 should find exactly 10 phantoms, got {len(findings)}"
        )

    def test_empty_api_data(self, tmp_path):
        """Empty api_data produces no findings."""
        findings = stage2_knowledge_validation(
            "test", "python", tmp_path, [], _make_id_fn,
        )
        assert findings == []

    def test_nonexistent_clone_path(self):
        """Nonexistent clone path produces no findings."""
        findings = stage2_knowledge_validation(
            "test", "python", Path("/nonexistent"), _make_api_data(5), _make_id_fn,
        )
        assert findings == []


# ---------------------------------------------------------------------------
# False-positive suppression (FIX-N4-01)
# ---------------------------------------------------------------------------

class TestApplyFalsePositives:
    def _finding(self, **kwargs) -> dict:
        base = {
            "type": "wrong-claim",
            "severity": "M",
            "file": "content/docs/index.md",
            "description": "Some description",
            "status": "open",
        }
        base.update(kwargs)
        return base

    def test_matching_finding_is_suppressed(self):
        findings = [self._finding(description="CfbDocument constructor issue")]
        rules = [{"id": "BUG-enet-001", "matches": {"description_contains": "CfbDocument"}}]
        n = _apply_false_positives(findings, "email", "net", rules)
        assert n == 1
        assert findings[0]["status"] == "suppressed"
        assert findings[0]["suppressed_by"] == "BUG-enet-001"

    def test_non_matching_description_not_suppressed(self):
        findings = [self._finding(description="Wrong package name")]
        rules = [{"id": "BUG-enet-001", "matches": {"description_contains": "CfbDocument"}}]
        n = _apply_false_positives(findings, "email", "net", rules)
        assert n == 0
        assert findings[0]["status"] == "open"

    def test_family_scope_restricts_match(self):
        findings = [self._finding(description="CfbDocument issue")]
        rules = [{"id": "BUG-enet-001", "matches": {"family": "email", "description_contains": "CfbDocument"}}]
        n = _apply_false_positives(findings, "cells", "net", rules)
        assert n == 0

    def test_platform_scope_restricts_match(self):
        findings = [self._finding(description="CfbDocument issue")]
        rules = [{"id": "BUG-enet-001", "matches": {"platform": "net", "description_contains": "CfbDocument"}}]
        n = _apply_false_positives(findings, "email", "python", rules)
        assert n == 0

    def test_already_suppressed_not_double_counted(self):
        findings = [self._finding(description="CfbDocument issue", status="suppressed")]
        rules = [{"id": "BUG-enet-001", "matches": {"description_contains": "CfbDocument"}}]
        n = _apply_false_positives(findings, "email", "net", rules)
        assert n == 0

    def test_empty_rules_changes_nothing(self):
        findings = [self._finding(description="CfbDocument issue")]
        n = _apply_false_positives(findings, "email", "net", [])
        assert n == 0
        assert findings[0]["status"] == "open"

    def test_suppressed_findings_excluded_from_verdict(self):
        findings = [
            self._finding(severity="M", status="suppressed"),
        ]
        result = compute_verdict(findings)
        assert result == "PUBLICATION READY"

    def test_wontfix_findings_excluded_from_verdict(self):
        findings = [
            self._finding(severity="M", status="wontfix"),
        ]
        result = compute_verdict(findings)
        assert result == "PUBLICATION READY"
