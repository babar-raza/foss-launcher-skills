"""Tests for page_impact_matrix.py (mission-plan-the-end-to-end-vast-hejlsberg.md
Task 2, S9.1, closes G7).
"""
from __future__ import annotations

import json
from pathlib import Path

import pytest
import yaml

import page_impact_matrix as pim

_REAL_REPO_ROOT = Path(__file__).resolve().parents[3]


@pytest.fixture(autouse=True)
def _reset_config():
    yield
    pim.configure()


def _write_json(path: Path, data) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(data), encoding="utf-8")


def _write_yaml(path: Path, data) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(yaml.dump(data), encoding="utf-8")


def _write_jsonl(path: Path, rows: list[dict]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text("\n".join(json.dumps(r) for r in rows) + "\n", encoding="utf-8")


def _seed_minimal_repo(tmp_path: Path, family="pdf", platform="java", run_id="rf-test-001"):
    """Seed the eight source artifacts with a small, coherent fixture: one
    page (docs) whose cited evidence matches one changed API, one page
    (blog) with no matching delta item at all."""
    run_root = tmp_path / "reports" / "refresh_runs" / family / platform / run_id

    _write_json(
        tmp_path / "knowledge" / family / platform / "merged" / "knowledge_delta.json",
        {
            "generated_at": "2026-08-21T00:00:00Z",
            "base_sha": "aaa",
            "current_sha": "bbb",
            "new_claims": [], "removed_claims": [], "modified_claims": [],
            "new_apis": ["Align"], "removed_apis": [], "modified_apis": [], "resurrected_apis": [],
        },
    )
    _write_json(
        tmp_path / "reports" / "refresh_review" / family / platform / "semantic_changes.json",
        [
            {
                "change_id": "CHG-1", "family": family, "platform": platform,
                "base_sha": "aaa", "current_sha": "bbb",
                "evidence_paths": [], "change_type": "API_ADDED",
                "symbol": "Align", "symbol_kind": "class",
                "public_impact": "USER_VISIBLE", "content_impact": "BODY_UPDATE",
                "confidence": 0.95,
            }
        ],
    )
    _write_json(
        tmp_path / "reports" / "refresh_review" / family / platform / "page_impact.json",
        {
            "family": family, "platform": platform, "delta_sha": "bbb",
            "pages": [
                {"path": "content/docs.aspose.org/en/pdf/java/_index.md", "subdomain": "docs",
                 "pia_score": "HIGH_IMPACT", "signals_found": ["cite-api:Align"]},
            ],
        },
    )
    _write_yaml(
        tmp_path / "reports" / "refresh_review" / family / platform / "triage_verdict.yaml",
        {
            "family": family, "platform": platform, "pages_checked": 1,
            "stale_count": 0, "error_count": 0, "unknown_count": 0,
            "results": [
                {"page_path": "content/blog.aspose.org/pdf/java/some-post/index.md",
                 "verdict": "not_stale", "stale": False, "reasons": ["no cited claims affected"]},
            ],
        },
    )
    _write_json(
        tmp_path / "data" / "package_registry.json",
        {family: {platform: {"verification": {"published": True}}}},
    )
    _write_json(
        run_root / "manifest.json",
        {"state": "VALIDATING", "updated_at": "2026-08-21T01:00:00Z", "commit_sha": None},
    )
    _write_jsonl(
        run_root / "page_decisions.jsonl",
        [
            {
                "page_path": "content/docs.aspose.org/en/pdf/java/_index.md",
                "surface": "docs", "disposition": "BODY_UPDATED",
                "body_hash_before": "sha256:old", "body_hash_after": "sha256:new",
                "receipt_ref": "receipts/RCP-docs.yaml",
                "evidence_claims_checked": [], "evidence_apis_checked": ["Align"],
                "validator_results": {"receipt": "PASS", "forbidden_claims": "PASS"},
            },
            {
                "page_path": "content/blog.aspose.org/pdf/java/some-post/index.md",
                "surface": "blog", "disposition": "NOT_AFFECTED",
                "body_hash_before": "sha256:same", "body_hash_after": "sha256:same",
                "receipt_ref": None,
                "evidence_claims_checked": [], "evidence_apis_checked": [],
                "validator_results": {"receipt": "PASS"},
            },
        ],
    )
    _write_yaml(
        run_root / "receipts" / "RCP-docs.yaml",
        {"content_refresh_receipt": {"receipt_id": "RCP-docs", "strategy_used": "BODY_UPDATE"}},
    )
    return run_root


# ---------------------------------------------------------------------------
# Loaders -- fail-open on missing artifacts
# ---------------------------------------------------------------------------

def test_loaders_fail_open_when_artifacts_missing(tmp_path):
    pim.configure(repo_root=tmp_path)
    assert pim.load_knowledge_delta("pdf", "java") is None
    assert pim.load_semantic_changes("pdf", "java") == []
    assert pim.load_page_impact("pdf", "java") is None
    assert pim.load_triage_verdict("pdf", "java") is None
    assert pim.load_publication_status("pdf", "java") is None
    assert pim.load_page_decisions(tmp_path / "reports" / "refresh_runs" / "pdf" / "java" / "no-such-run") == []
    assert pim.load_oracle_verdicts("pdf", "java") == {}
    assert pim.load_manifest(tmp_path / "reports" / "refresh_runs" / "pdf" / "java" / "no-such-run") is None


def test_publication_status_distinguishes_false_from_missing(tmp_path):
    pim.configure(repo_root=tmp_path)
    _write_json(tmp_path / "data" / "package_registry.json", {"pdf": {"java": {"verification": {"published": False}}}})
    assert pim.load_publication_status("pdf", "java") is False
    assert pim.load_publication_status("pdf", "net") is None  # no entry at all


# ---------------------------------------------------------------------------
# Full join correctness
# ---------------------------------------------------------------------------

def test_build_matrix_full_join(tmp_path):
    pim.configure(repo_root=tmp_path)
    _seed_minimal_repo(tmp_path)

    matrix = pim.build_matrix("pdf", "java", "rf-test-001")

    assert matrix["family"] == "pdf"
    assert matrix["platform"] == "java"
    assert matrix["run_id"] == "rf-test-001"
    assert matrix["row_count"] == 2
    assert matrix["knowledge_current_sha"] == "bbb"

    rows_by_page = {r["affected_repo_page"]: r for r in matrix["rows"]}

    docs_row = rows_by_page["content/docs.aspose.org/en/pdf/java/_index.md"]
    assert docs_row["affected_surface"] == "docs"
    assert docs_row["required_action"] == "update"
    assert docs_row["release_delta_item"] == ["Align"]
    assert docs_row["change_classification"] == ["API_ADDED"]
    assert docs_row["reason_for_no_change"] is None
    assert docs_row["prose_updated"] is True
    assert docs_row["code_updated"] == "unknown"  # BODY_UPDATE strategy, not a full regen
    assert docs_row["publication_dependency"] == "published"
    assert "PENDING" in docs_row["final_evidence"]  # run state is VALIDATING, not COMMITTED

    blog_row = rows_by_page["content/blog.aspose.org/pdf/java/some-post/index.md"]
    assert blog_row["required_action"] == "no_change"
    assert blog_row["release_delta_item"] is None
    assert blog_row["reason_for_no_change"] == "no cited claims affected"  # from triage_verdict
    assert blog_row["prose_updated"] is False
    assert blog_row["code_updated"] == "false"
    assert blog_row["publication_dependency"] is None  # blog surface, no install command

    assert matrix["incomplete_row_count"] == 0  # every no_change row got a real reason


def test_no_change_row_falls_back_to_generic_reason_without_triage_verdict(tmp_path):
    """A page with no matched delta item and no corresponding triage_verdict
    entry at all must still get a real, non-empty reason -- never a silently
    incomplete row (SS16's own failure-condition standard)."""
    pim.configure(repo_root=tmp_path)
    run_root = tmp_path / "reports" / "refresh_runs" / "pdf" / "java" / "rf-test-002"
    _write_jsonl(
        run_root / "page_decisions.jsonl",
        [{
            "page_path": "content/kb.aspose.org/en/pdf/java/some-howto.md",
            "surface": "kb", "disposition": "NOT_AFFECTED",
            "body_hash_before": "x", "body_hash_after": "x",
            "receipt_ref": None, "evidence_claims_checked": [], "evidence_apis_checked": [],
            "validator_results": {},
        }],
    )
    matrix = pim.build_matrix("pdf", "java", "rf-test-002")
    row = matrix["rows"][0]
    assert row["required_action"] == "no_change"
    assert row["reason_for_no_change"]
    assert matrix["incomplete_row_count"] == 0


def test_committed_run_reports_real_final_evidence(tmp_path):
    pim.configure(repo_root=tmp_path)
    run_root = _seed_minimal_repo(tmp_path, run_id="rf-test-003")
    manifest = json.loads((run_root / "manifest.json").read_text(encoding="utf-8"))
    manifest["state"] = "COMMITTED"
    manifest["commit_sha"] = "deadbeef"
    _write_json(run_root / "manifest.json", manifest)

    matrix = pim.build_matrix("pdf", "java", "rf-test-003")
    docs_row = next(r for r in matrix["rows"] if r["affected_surface"] == "docs")
    assert "COMMITTED at deadbeef" in docs_row["final_evidence"]


def test_code_updated_true_for_reference_regeneration_strategy(tmp_path):
    pim.configure(repo_root=tmp_path)
    run_root = tmp_path / "reports" / "refresh_runs" / "pdf" / "java" / "rf-test-004"
    _write_jsonl(
        run_root / "page_decisions.jsonl",
        [{
            "page_path": "content/reference.aspose.org/en/pdf/java/Align.md",
            "surface": "reference", "disposition": "GENERATED",
            "body_hash_before": "x", "body_hash_after": "y",
            "receipt_ref": "receipts/RCP-ref.yaml",
            "evidence_claims_checked": [], "evidence_apis_checked": [],
            "validator_results": {},
        }],
    )
    _write_yaml(
        run_root / "receipts" / "RCP-ref.yaml",
        {"content_refresh_receipt": {"receipt_id": "RCP-ref", "strategy_used": "REFERENCE_REGENERATION"}},
    )
    matrix = pim.build_matrix("pdf", "java", "rf-test-004")
    row = matrix["rows"][0]
    assert row["prose_updated"] is True
    assert row["code_updated"] == "true"
    assert row["publication_dependency"] is None  # reference surface, no install command


# ---------------------------------------------------------------------------
# Report writing + rendering
# ---------------------------------------------------------------------------

def test_write_matrix_report_creates_json_and_markdown(tmp_path):
    pim.configure(repo_root=tmp_path)
    _seed_minimal_repo(tmp_path)

    json_path, md_path = pim.write_matrix_report("pdf", "java", "rf-test-001")

    assert json_path == tmp_path / "reports" / "refresh_review" / "pdf" / "java" / "page_impact_matrix.json"
    assert json_path.is_file()
    assert md_path.is_file()

    written = json.loads(json_path.read_text(encoding="utf-8"))
    assert written["row_count"] == 2

    md_text = md_path.read_text(encoding="utf-8")
    assert "pdf/java" in md_text
    assert "content/docs.aspose.org/en/pdf/java/_index.md" in md_text
    assert "content/blog.aspose.org/pdf/java/some-post/index.md" in md_text


def test_matrix_digest_matches_written_file(tmp_path):
    pim.configure(repo_root=tmp_path)
    _seed_minimal_repo(tmp_path)
    json_path, _ = pim.write_matrix_report("pdf", "java", "rf-test-001")

    digest = pim.matrix_digest(json_path)
    assert digest is not None
    assert digest.startswith("sha256:")
    assert pim.matrix_digest(tmp_path / "does-not-exist.json") is None


def test_render_markdown_flags_incomplete_rows_section(tmp_path):
    matrix = {
        "family": "pdf", "platform": "java", "run_id": "r1",
        "run_state": "VALIDATING", "knowledge_current_sha": "bbb",
        "row_count": 1, "incomplete_row_count": 1,
        "incomplete_rows": ["content/docs.aspose.org/en/pdf/java/x.md"],
        "rows": [{
            "affected_repo_page": "content/docs.aspose.org/en/pdf/java/x.md",
            "affected_surface": "docs", "required_action": "preserve",
            "release_delta_item": None, "change_classification": None,
            "reason_for_no_change": None, "prose_updated": False, "code_updated": "false",
            "validator_test": None, "final_evidence": "PENDING",
        }],
    }
    md = pim.render_markdown(matrix)
    assert "Incomplete rows" in md
    assert "content/docs.aspose.org/en/pdf/java/x.md" in md


# ---------------------------------------------------------------------------
# Real-data smoke test (SS15: "use this as a real-data validation pass in
# addition to synthetic fixtures" -- against the real, on-disk 936KB fixture)
# ---------------------------------------------------------------------------

def test_load_semantic_changes_against_real_pdf_java_fixture():
    real_fixture = _REAL_REPO_ROOT / "reports" / "refresh_review" / "pdf" / "java" / "semantic_changes.json"
    if not real_fixture.is_file():
        pytest.skip("real pdf/java semantic_changes.json fixture not present in this checkout")
    pim.configure(repo_root=_REAL_REPO_ROOT)
    changes = pim.load_semantic_changes("pdf", "java")
    assert len(changes) > 1000  # the plan cites 1,835 typed changes
    sample = changes[0]
    assert set(sample) >= {
        "change_id", "family", "platform", "base_sha", "current_sha",
        "evidence_paths", "change_type", "symbol", "symbol_kind",
        "public_impact", "content_impact", "confidence",
    }
