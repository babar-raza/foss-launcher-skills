"""Tests for gap-eval's missing-profile loud-failure fix -- RC-tex-python-04 /
Phase A (MT037-2026-08-24-FOSS-PORTFOLIO-FORENSIC-HEAL blind-spot audit).

Bug: a missing profile at scripts/gap-eval/profiles/{family}/{platform}.yaml
used to silently fall back to "minimal defaults" with only a log.warning()
call -- the run could still report a clean PUBLICATION READY verdict even
though most Tier 1 checks are degraded or skipped in that mode. Confirmed
live: tex/python (no profile) returned PUBLICATION READY with only 7
"missing optional page" findings, catching 0 of 9 real content defects an
unaided review found.
"""

from __future__ import annotations

import sys
from pathlib import Path

import pytest

_GAP_EVAL_DIR = Path(__file__).resolve().parents[2] / "gap-eval" / "src"
if str(_GAP_EVAL_DIR) not in sys.path:
    sys.path.insert(0, str(_GAP_EVAL_DIR))

import run as gap_eval_run  # type: ignore  # noqa: E402


class TestMissingProfileFinding:
    def test_finding_shape_is_valid(self):
        finding = gap_eval_run._missing_profile_finding("tex", "python")
        assert finding["type"] == "missing-profile-degraded-mode"
        assert finding["severity"] == "S"
        assert finding["status"] == "open"
        assert "tex" in finding["file"] and "python" in finding["file"]
        assert "tex" in finding["description"] or "python" in finding["description"]

    def test_finding_id_is_deterministic(self):
        """Same family/platform must always produce the same finding ID, so
        the state-merge logic can correctly recognize it as the same finding
        across reruns rather than duplicating it."""
        f1 = gap_eval_run._missing_profile_finding("tex", "python")
        f2 = gap_eval_run._missing_profile_finding("tex", "python")
        assert f1["id"] == f2["id"]

    def test_different_products_get_different_ids(self):
        f1 = gap_eval_run._missing_profile_finding("tex", "python")
        f2 = gap_eval_run._missing_profile_finding("barcode", "python")
        assert f1["id"] != f2["id"]


class TestComputeVerdictCapsOnMissingProfile:
    def test_s_severity_missing_profile_finding_forces_conditional(self):
        """The exact real-world regression: a run with ONLY the missing-profile
        finding (no other real findings at all) must NOT report PUBLICATION
        READY -- it must be capped at CONDITIONAL."""
        finding = gap_eval_run._missing_profile_finding("tex", "python")
        verdict = gap_eval_run.compute_verdict([finding])
        assert verdict != "PUBLICATION READY"
        assert verdict == "CONDITIONAL"

    def test_no_findings_still_reports_publication_ready(self):
        """Negative control: with a real profile (no missing-profile finding
        injected) and zero other findings, the verdict is unaffected."""
        assert gap_eval_run.compute_verdict([]) == "PUBLICATION READY"


class TestProfileMissingDetectionInRun:
    """Exercises the module's own configure(repo_root=...) seam so
    _profile_path's real path-joining logic runs against a scratch repo
    root, rather than mocking the function itself (AGENTS.md 16)."""

    @pytest.fixture(autouse=True)
    def _reset_configure(self):
        yield
        gap_eval_run.configure(repo_root=None)

    def test_profile_missing_flag_true_when_file_absent(self, tmp_path):
        gap_eval_run.configure(repo_root=tmp_path)
        assert not gap_eval_run._profile_path("tex", "python").exists()

    def test_profile_missing_flag_false_when_file_present(self, tmp_path):
        profile_dir = tmp_path / "scripts" / "gap-eval" / "profiles" / "tex"
        profile_dir.mkdir(parents=True)
        (profile_dir / "python.yaml").write_text("family: tex\nplatform: python\n", encoding="utf-8")
        gap_eval_run.configure(repo_root=tmp_path)
        assert gap_eval_run._profile_path("tex", "python").exists()
