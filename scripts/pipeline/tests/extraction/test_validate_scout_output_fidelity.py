"""Tests for extraction/validate_scout_output.py's TC-MT040-41 (D-2)
extension: an optional, purely-additive `fidelity` summary block folded in
from a scout_fidelity.py fidelity_report.json.

Regression requirement: every existing call shape (no fidelity_report arg)
must be byte-identical to before this extension — see
TestBackwardCompatibility below, which pins the exact pre-extension return
shape for both the OK and EXTRACTION_FAILURE branches.
"""
from __future__ import annotations

import json
from pathlib import Path

from extraction.validate_scout_output import (
    _summarize_fidelity,
    main,
    validate_scout_output,
)


def _fidelity_report(*, overall_status="WARN", findings_count=1, fail_count=0) -> dict:
    return {
        "schema_version": 1,
        "family": "fake",
        "platform": "typescript",
        "clone_available": True,
        "overall_status": overall_status,
        "findings_count": findings_count,
        "fail_count": fail_count,
        "probes": {
            "P1": {"status": "WARN", "message": "1 declaration missing", "details": {"x": 1}},
            "P2": {"status": "OK", "message": "all present", "details": {}},
        },
    }


class TestBackwardCompatibility:
    """No fidelity_report arg -> return shape unchanged from before this card."""

    def test_ok_branch_has_no_fidelity_key_by_default(self, tmp_path: Path):
        result = validate_scout_output({"stats": {"class_count": 5, "total_claims": 30}}, tmp_path, "python")
        assert result["verdict"] == "OK"
        assert "fidelity" not in result

    def test_extraction_failure_branch_has_no_fidelity_key_by_default(self, tmp_path: Path):
        (tmp_path / "thing.rs").write_text("pub struct Thing {}\n", encoding="utf-8")
        result = validate_scout_output({"stats": {"class_count": 0}}, tmp_path, "rust")
        assert result["verdict"] == "EXTRACTION_FAILURE"
        assert "fidelity" not in result

    def test_pre_alpha_branch_has_no_fidelity_key_by_default(self, tmp_path: Path):
        result = validate_scout_output({"stats": {"class_count": 0}}, tmp_path, "rust")
        assert result["verdict"] == "PRE_ALPHA"
        assert "fidelity" not in result


class TestFidelitySummaryAdditive:
    def test_fidelity_block_added_without_changing_verdict(self, tmp_path: Path):
        result = validate_scout_output(
            {"stats": {"class_count": 5, "total_claims": 30}}, tmp_path, "python",
            fidelity_report=_fidelity_report(),
        )
        assert result["verdict"] == "OK"  # unchanged by the fidelity finding
        assert result["tier"] == "minimal"  # 5 classes/30 claims -> minimal per _TIERS
        assert "fidelity" in result
        assert result["fidelity"]["overall_status"] == "WARN"
        assert result["fidelity"]["findings_count"] == 1
        assert result["fidelity"]["probe_statuses"] == {"P1": "WARN", "P2": "OK"}

    def test_fidelity_block_never_flips_verdict_even_on_fail(self, tmp_path: Path):
        """A hypothetical future FAIL-enabled probe still must not change
        validate_scout_output's own verdict -- that gate's semantics
        (class_count vs class-bearing files) are independent of fidelity."""
        result = validate_scout_output(
            {"stats": {"class_count": 5, "total_claims": 30}}, tmp_path, "python",
            fidelity_report=_fidelity_report(overall_status="FAIL", fail_count=1),
        )
        assert result["verdict"] == "OK"
        assert result["fidelity"]["overall_status"] == "FAIL"

    def test_summarize_fidelity_drops_nested_probe_details(self):
        summary = _summarize_fidelity(_fidelity_report())
        assert "details" not in json.dumps(summary)  # only probe_statuses survive, not full per-probe payloads
        assert summary["probe_statuses"]["P1"] == "WARN"


class TestCliFidelityFlag:
    def test_cli_prints_fidelity_line_when_report_given(self, tmp_path: Path, capsys):
        model_yaml = tmp_path / "model.yaml"
        model_yaml.write_text("stats:\n  class_count: 5\n  total_claims: 30\n", encoding="utf-8")
        fidelity_path = tmp_path / "fidelity_report.json"
        fidelity_path.write_text(json.dumps(_fidelity_report()), encoding="utf-8")
        repo_dir = tmp_path / "repo"
        repo_dir.mkdir()

        rc = main([str(model_yaml), str(repo_dir), "python", "--fidelity-report", str(fidelity_path)])
        assert rc == 0
        out = capsys.readouterr().out
        assert "FIDELITY: WARN" in out

    def test_cli_json_includes_fidelity_key(self, tmp_path: Path, capsys):
        model_yaml = tmp_path / "model.yaml"
        model_yaml.write_text("stats:\n  class_count: 5\n  total_claims: 30\n", encoding="utf-8")
        fidelity_path = tmp_path / "fidelity_report.json"
        fidelity_path.write_text(json.dumps(_fidelity_report()), encoding="utf-8")
        repo_dir = tmp_path / "repo"
        repo_dir.mkdir()

        rc = main([str(model_yaml), str(repo_dir), "python", "--fidelity-report", str(fidelity_path), "--json"])
        assert rc == 0
        out = json.loads(capsys.readouterr().out)
        assert out["fidelity"]["overall_status"] == "WARN"
