"""Tests for product_acceptance_state.py (R-1, MT040-2026-08-28-PDF-TYPESCRIPT-LAUNCH
TC-MT040-49) -- read-only acceptance-state projection.

Coverage:
- no artifacts at all -> overall_status no_acceptance_artifact_found, exit 1
- readiness.md only, no bindings -> unverifiable
- readiness.md only, bindings current -> current
- readiness.md only, bindings stale -> stale_verdict
- readiness.md + final-verdict.md agree (both accept) -> not artifacts_disagree
- readiness.md + final-verdict.md disagree -> artifacts_disagree (reproduces
  the real, live cells/typescript contradiction found this session)
- final-verdict.md verdict parsing matches the real report shape
  ("## Final Recommendation" heading + "**PUBLISH**" bold line)
- hgate bindings summary reads real sample files
- never raises on a malformed/partial artifact
"""
from __future__ import annotations

import pytest

import product_acceptance_state as product_state


@pytest.fixture(autouse=True)
def _reset_ps():
    yield
    product_state.configure()


def _write_model(tmp_path, family, platform, repo_sha):
    d = tmp_path / "knowledge" / family / platform / "merged"
    d.mkdir(parents=True, exist_ok=True)
    (d / "model.yaml").write_text(f"repo_sha: {repo_sha}\n", encoding="utf-8")


def _write_readiness_md(tmp_path, family, platform, verdict, bindings_block=""):
    d = tmp_path / "reports" / family / platform
    d.mkdir(parents=True, exist_ok=True)
    text = f"# Readiness Scorecard: {family}/{platform}\n\n**Verdict**: {verdict}\n\n"
    if bindings_block:
        text += f"```yaml\n{bindings_block}\n```\n\n"
    (d / "readiness.md").write_text(text, encoding="utf-8")


def _write_final_verdict_md(tmp_path, family, platform, date, verdict, bindings_block=""):
    d = tmp_path / "reports" / "publish-review" / f"{family}-{platform}-{date}"
    d.mkdir(parents=True, exist_ok=True)
    text = (
        f"# Publish Readiness Verdict — {family}/{platform}\n"
        f"**Date**: {date}\n\n"
        f"## Final Recommendation\n\n**{verdict}**\n\n"
        f"Some summary prose.\n"
    )
    if bindings_block:
        text += f"\n```yaml\n{bindings_block}\n```\n"
    (d / "final-verdict.md").write_text(text, encoding="utf-8")


class TestNoArtifacts:
    def test_no_artifacts_found(self, tmp_path):
        product_state.configure(repo_root=tmp_path)
        state = product_state.compute_product_state("pdf", "typescript")
        assert state["overall_status"] == "no_acceptance_artifact_found"
        assert state["readiness_md"]["path"] is None
        assert state["final_verdict_md"]["path"] is None

    def test_main_exits_1_when_no_artifacts(self, tmp_path, monkeypatch, capsys):
        product_state.configure(repo_root=tmp_path)
        # T3-MOCK: target=sys.argv reason="CLI main() does not accept argv param" removal=PERMANENT
        monkeypatch.setattr("sys.argv", ["product_acceptance_state.py", "--family", "pdf", "--platform", "typescript"])
        with pytest.raises(SystemExit) as exc:
            product_state.main()
        assert exc.value.code == 1


class TestReadinessOnly:
    def test_no_bindings_block_is_unverifiable(self, tmp_path):
        _write_model(tmp_path, "pdf", "typescript", "sha1")
        _write_readiness_md(tmp_path, "pdf", "typescript", "READY TO SHIP")
        product_state.configure(repo_root=tmp_path)
        state = product_state.compute_product_state("pdf", "typescript")
        assert state["readiness_md"]["verdict"] == "READY TO SHIP"
        assert state["readiness_md"]["bindings_status"] == "unverifiable"
        assert state["overall_status"] == "unverifiable"

    def test_matching_bindings_is_current(self, tmp_path):
        _write_model(tmp_path, "pdf", "typescript", "sha1")
        _write_readiness_md(
            tmp_path, "pdf", "typescript", "READY TO SHIP",
            bindings_block='bindings:\n  model_sha: "sha1"',
        )
        product_state.configure(repo_root=tmp_path)
        state = product_state.compute_product_state("pdf", "typescript")
        assert state["readiness_md"]["bindings_status"] == "current"
        assert state["overall_status"] == "current"

    def test_mismatched_bindings_is_stale(self, tmp_path):
        _write_model(tmp_path, "pdf", "typescript", "sha_new")
        _write_readiness_md(
            tmp_path, "pdf", "typescript", "READY TO SHIP",
            bindings_block='bindings:\n  model_sha: "sha_old"',
        )
        product_state.configure(repo_root=tmp_path)
        state = product_state.compute_product_state("pdf", "typescript")
        assert state["readiness_md"]["bindings_status"] == "stale"
        assert state["overall_status"] == "stale_verdict"


class TestFinalVerdictParsing:
    def test_publish_verdict_parsed_from_real_shape(self, tmp_path):
        """Matches the real report shape at
        reports/publish-review/3d-typescript-20260606/final-verdict.md:
        a '## Final Recommendation' heading, blank line, '**PUBLISH**'."""
        _write_final_verdict_md(tmp_path, "3d", "typescript", "20260606", "PUBLISH")
        product_state.configure(repo_root=tmp_path)
        state = product_state.compute_product_state("3d", "typescript")
        assert state["final_verdict_md"]["verdict"] == "PUBLISH"

    def test_picks_most_recent_when_multiple_reviews_exist(self, tmp_path):
        _write_final_verdict_md(tmp_path, "pdf", "typescript", "20260101", "BLOCKED")
        import time
        time.sleep(0.01)
        _write_final_verdict_md(tmp_path, "pdf", "typescript", "20260201", "PUBLISH")
        product_state.configure(repo_root=tmp_path)
        state = product_state.compute_product_state("pdf", "typescript")
        assert state["final_verdict_md"]["verdict"] == "PUBLISH"
        assert "20260201" in state["final_verdict_md"]["path"]


class TestArtifactAgreement:
    def test_agreeing_verdicts_not_flagged(self, tmp_path):
        _write_readiness_md(tmp_path, "3d", "typescript", "READY TO SHIP")
        _write_final_verdict_md(tmp_path, "3d", "typescript", "20260606", "PUBLISH")
        product_state.configure(repo_root=tmp_path)
        state = product_state.compute_product_state("3d", "typescript")
        assert state["artifacts_agree"] is True
        assert state["overall_status"] != "artifacts_disagree"

    def test_disagreeing_verdicts_flagged_reproduces_real_cells_typescript_case(self, tmp_path):
        """Reproduces the real, live contradiction found this session:
        cells/typescript's readiness.md said NOT READY while its own
        final-verdict.md said PUBLISH -- both true at the same time on disk,
        undetected until a human happened to compare dates by hand."""
        _write_readiness_md(tmp_path, "cells", "typescript", "NOT READY")
        _write_final_verdict_md(tmp_path, "cells", "typescript", "20260606", "PUBLISH")
        product_state.configure(repo_root=tmp_path)
        state = product_state.compute_product_state("cells", "typescript")
        assert state["artifacts_agree"] is False
        assert state["overall_status"] == "artifacts_disagree"


class TestHGateBindingsSummary:
    def test_reads_real_sample_files(self, tmp_path):
        _write_model(tmp_path, "pdf", "typescript", "sha1")
        review_dir = tmp_path / "reports" / "human-review"
        review_dir.mkdir(parents=True)
        (review_dir / "pdf-typescript-h01-sample.md").write_text(
            '```yaml\nresult: "PASS"\nbindings:\n  model_sha: "sha1"\n```\n'
        )
        product_state.configure(repo_root=tmp_path)
        state = product_state.compute_product_state("pdf", "typescript")
        assert state["hgate_bindings_status"]["h01"] == "current"
        assert state["hgate_bindings_status"]["h02"] == "no_sample_file"

    def test_never_raises_on_malformed_sample_file(self, tmp_path):
        review_dir = tmp_path / "reports" / "human-review"
        review_dir.mkdir(parents=True)
        (review_dir / "pdf-typescript-h01-sample.md").write_text("not valid yaml at all {{{")
        product_state.configure(repo_root=tmp_path)
        # Must not raise.
        state = product_state.compute_product_state("pdf", "typescript")
        assert state["hgate_bindings_status"]["h01"] == "unverifiable"


class TestJsonOutput:
    def test_json_output_is_valid_and_matches_dict(self, tmp_path, monkeypatch, capsys):
        _write_readiness_md(tmp_path, "pdf", "typescript", "READY TO SHIP")
        product_state.configure(repo_root=tmp_path)
        # T3-MOCK: target=sys.argv reason="CLI main() does not accept argv param" removal=PERMANENT
        monkeypatch.setattr("sys.argv", ["product_acceptance_state.py", "--family", "pdf",
                                         "--platform", "typescript", "--json"])
        with pytest.raises(SystemExit) as exc:
            product_state.main()
        assert exc.value.code == 0
        import json
        out = capsys.readouterr().out
        data = json.loads(out)
        assert data["family"] == "pdf"
        assert data["readiness_md"]["verdict"] == "READY TO SHIP"
