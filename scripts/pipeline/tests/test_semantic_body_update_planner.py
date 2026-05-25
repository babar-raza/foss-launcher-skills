"""Tests for semantic_body_update_planner.py"""

import json
import tempfile
from pathlib import Path
import pytest

from commands.ops.semantic_body_update_planner import (
    plan,
    _is_generated_reference_page,
    _subdomain_from_path,
    _page_priority,
    _ALL_ZERO_SHA,
    _DECISION_BODY_UPDATE_REQUIRED,
    _DECISION_SOURCE_EVIDENCE_UNAVAILABLE,
    _DECISION_PAGE_MAPPING_GAP,
    _DECISION_CLAIM_EXTRACTION_GAP,
    main,
)


# ─── Helpers ──────────────────────────────────────────────────────────────────

def _make_page_impact(entries: list[dict]) -> dict:
    return {"pages": entries}


def _make_page_decisions(pages: dict) -> dict:
    return {"pages": pages}


def _make_source_delta(old_sha: str = "abc123", diff: bool = True) -> dict:
    return {
        "old_source_sha": old_sha,
        "new_source_sha": "def456",
        "diff_available": diff,
        "source_change_impact": "HIGH",
        "claim_delta_detail": {"new_claims": 5, "modified_claims": 2, "removed_claims": 1},
    }


def _make_knowledge_delta(new: int = 5, modified: int = 2, removed: int = 1) -> dict:
    return {
        "new_claims": [f"CLM-{i:06x}" for i in range(new)],
        "modified_claims": [f"CLM-MOD-{i:06x}" for i in range(modified)],
        "removed_claims": [f"CLM-REM-{i:06x}" for i in range(removed)],
    }


def _write_json(path: Path, data: dict) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(data), encoding="utf-8")


# ─── Unit tests ───────────────────────────────────────────────────────────────

class TestHelpers:
    def test_is_generated_reference_page_true(self):
        assert _is_generated_reference_page("content/reference.aspose.org/en/font/python/FontLoader.md")

    def test_is_generated_reference_page_false_docs(self):
        assert not _is_generated_reference_page("content/docs.aspose.org/en/font/python/developer-guide/features.md")

    def test_is_generated_reference_page_false_kb(self):
        assert not _is_generated_reference_page("content/kb.aspose.org/en/font/python/faq.md")

    def test_subdomain_from_path_docs(self):
        assert _subdomain_from_path("content/docs.aspose.org/en/foo") == "docs.aspose.org"

    def test_subdomain_from_path_kb(self):
        assert _subdomain_from_path("content/kb.aspose.org/en/foo") == "kb.aspose.org"

    def test_subdomain_from_path_reference(self):
        assert _subdomain_from_path("content/reference.aspose.org/en/foo") == "reference.aspose.org"

    def test_page_priority_docs_before_kb(self):
        assert _page_priority("content/docs.aspose.org/en/x") < _page_priority("content/kb.aspose.org/en/x")

    def test_page_priority_reference_last(self):
        assert _page_priority("content/reference.aspose.org/en/x") > _page_priority("content/docs.aspose.org/en/x")
        assert _page_priority("content/reference.aspose.org/en/x") > _page_priority("content/kb.aspose.org/en/x")


# ─── Integration-level plan() tests ───────────────────────────────────────────

class TestPlannerCoreLogic:

    def _run_plan(self, page_impact, page_decisions, source_delta=None, knowledge_delta=None,
                  max_pages=10, include_reference=False):
        with tempfile.TemporaryDirectory() as tmpdir:
            base = Path(tmpdir)
            pi_path = base / "page_impact.json"
            pd_path = base / "page_decisions.json"
            sd_path = base / "source_delta.json"
            kd_path = base / "knowledge_delta.json"

            _write_json(pi_path, page_impact)
            _write_json(pd_path, page_decisions)
            _write_json(sd_path, source_delta or _make_source_delta())
            _write_json(kd_path, knowledge_delta or _make_knowledge_delta())

            return plan(
                family="font", platform="python",
                source_delta_path=sd_path, page_impact_path=pi_path,
                knowledge_delta_path=kd_path, page_decisions_path=pd_path,
                max_pages=max_pages, include_reference=include_reference,
            )

    def test_generated_only_body_changes_not_counted_as_existing_update(self):
        """font/python masking: reference pages changed, docs pages still EVIDENCE_ONLY."""
        pi = _make_page_impact([
            {"path": "content/reference.aspose.org/en/font/python/FontCleaner.md",
             "pia_score": "HIGH_IMPACT", "signals_found": ["api:fontcleaner"]},
            {"path": "content/docs.aspose.org/en/font/python/developer-guide/features.md",
             "pia_score": "HIGH_IMPACT", "signals_found": ["api:fontcleaner"]},
        ])
        pd = _make_page_decisions({
            "content/reference.aspose.org/en/font/python/FontCleaner.md": {
                "decision": "BODY_UPDATED", "body_hash_changed": True},
            "content/docs.aspose.org/en/font/python/developer-guide/features.md": {
                "decision": "EVIDENCE_ONLY", "body_hash_changed": False},
        })
        result = self._run_plan(pi, pd)
        # Reference page is excluded; docs page should be selected
        assert result["pages_selected"] == 1
        assert result["pages"][0]["path"] == "content/docs.aspose.org/en/font/python/developer-guide/features.md"
        assert result["pages"][0]["per_page_decision"] == _DECISION_BODY_UPDATE_REQUIRED

    def test_high_impact_docs_kb_pages_are_selected(self):
        pi = _make_page_impact([
            {"path": "content/docs.aspose.org/en/font/python/developer-guide/features.md",
             "pia_score": "HIGH_IMPACT", "signals_found": ["api:fontcleaner"]},
            {"path": "content/kb.aspose.org/en/font/python/faq.md",
             "pia_score": "HIGH_IMPACT", "signals_found": ["api:ttffont"]},
        ])
        pd = _make_page_decisions({
            "content/docs.aspose.org/en/font/python/developer-guide/features.md":
                {"decision": "EVIDENCE_ONLY", "body_hash_changed": False},
            "content/kb.aspose.org/en/font/python/faq.md":
                {"decision": "EVIDENCE_ONLY", "body_hash_changed": False},
        })
        result = self._run_plan(pi, pd)
        paths = [p["path"] for p in result["pages"]]
        assert "content/docs.aspose.org/en/font/python/developer-guide/features.md" in paths
        assert "content/kb.aspose.org/en/font/python/faq.md" in paths

    def test_reference_pages_excluded_by_default(self):
        pi = _make_page_impact([
            {"path": "content/reference.aspose.org/en/font/python/FontLoader.md",
             "pia_score": "HIGH_IMPACT", "signals_found": ["api:fontloader"]},
        ])
        pd = _make_page_decisions({
            "content/reference.aspose.org/en/font/python/FontLoader.md":
                {"decision": "EVIDENCE_ONLY", "body_hash_changed": False},
        })
        result = self._run_plan(pi, pd, include_reference=False)
        assert result["pages_selected"] == 0
        assert result["overall_status"] == "NO_IMPACTED_EXISTING_PAGES"

    def test_reference_pages_included_when_flag_set(self):
        pi = _make_page_impact([
            {"path": "content/reference.aspose.org/en/font/python/FontLoader.md",
             "pia_score": "HIGH_IMPACT", "signals_found": ["api:fontloader"]},
        ])
        pd = _make_page_decisions({
            "content/reference.aspose.org/en/font/python/FontLoader.md":
                {"decision": "EVIDENCE_ONLY", "body_hash_changed": False},
        })
        result = self._run_plan(pi, pd, include_reference=True)
        assert result["pages_selected"] == 1

    def test_missing_page_impact_fails_closed(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            base = Path(tmpdir)
            pd_path = base / "page_decisions.json"
            _write_json(pd_path, _make_page_decisions({}))
            result = plan(
                family="font", platform="python",
                source_delta_path=base / "nonexistent.json",
                page_impact_path=base / "nonexistent_pi.json",
                knowledge_delta_path=base / "nonexistent_kd.json",
                page_decisions_path=pd_path,
                max_pages=10, include_reference=False,
            )
            assert result["status"] == "BLOCKED"

    def test_all_zero_old_sha_classified_as_source_baseline_missing(self):
        pi = _make_page_impact([
            {"path": "content/docs.aspose.org/en/cells/net/features.md",
             "pia_score": "HIGH_IMPACT", "signals_found": ["api:workbook"]},
        ])
        pd = _make_page_decisions({
            "content/docs.aspose.org/en/cells/net/features.md":
                {"decision": "EVIDENCE_ONLY", "body_hash_changed": False},
        })
        sd = _make_source_delta(old_sha=_ALL_ZERO_SHA, diff=False)
        result = self._run_plan(pi, pd, source_delta=sd)
        assert result["source_baseline_missing"] is True
        assert result["pages"][0]["per_page_decision"] == _DECISION_SOURCE_EVIDENCE_UNAVAILABLE

    def test_zero_body_match_signals_creates_page_mapping_gap(self):
        pi = _make_page_impact([
            {"path": "content/docs.aspose.org/en/font/python/developer-guide/features.md",
             "pia_score": "HIGH_IMPACT", "signals_found": []},
        ])
        pd = _make_page_decisions({
            "content/docs.aspose.org/en/font/python/developer-guide/features.md":
                {"decision": "EVIDENCE_ONLY", "body_hash_changed": False},
        })
        result = self._run_plan(pi, pd)
        assert result["pages"][0]["per_page_decision"] == _DECISION_PAGE_MAPPING_GAP

    def test_no_claim_delta_creates_claim_extraction_gap(self):
        pi = _make_page_impact([
            {"path": "content/docs.aspose.org/en/font/python/developer-guide/features.md",
             "pia_score": "HIGH_IMPACT", "signals_found": ["api:fontcleaner"]},
        ])
        pd = _make_page_decisions({
            "content/docs.aspose.org/en/font/python/developer-guide/features.md":
                {"decision": "EVIDENCE_ONLY", "body_hash_changed": False},
        })
        kd = _make_knowledge_delta(new=0, modified=0, removed=0)
        result = self._run_plan(pi, pd, knowledge_delta=kd)
        assert result["pages"][0]["per_page_decision"] == _DECISION_CLAIM_EXTRACTION_GAP

    def test_docs_selected_before_kb(self):
        pi = _make_page_impact([
            {"path": "content/kb.aspose.org/en/font/python/faq.md",
             "pia_score": "HIGH_IMPACT", "signals_found": ["api:ttffont"]},
            {"path": "content/docs.aspose.org/en/font/python/developer-guide/features.md",
             "pia_score": "HIGH_IMPACT", "signals_found": ["api:fontcleaner"]},
        ])
        pd = _make_page_decisions({
            "content/docs.aspose.org/en/font/python/developer-guide/features.md":
                {"decision": "EVIDENCE_ONLY", "body_hash_changed": False},
            "content/kb.aspose.org/en/font/python/faq.md":
                {"decision": "EVIDENCE_ONLY", "body_hash_changed": False},
        })
        result = self._run_plan(pi, pd, max_pages=2)
        assert result["pages"][0]["subdomain"] == "docs.aspose.org"
        assert result["pages"][1]["subdomain"] == "kb.aspose.org"

    def test_already_body_updated_pages_excluded(self):
        pi = _make_page_impact([
            {"path": "content/docs.aspose.org/en/font/python/developer-guide/features.md",
             "pia_score": "HIGH_IMPACT", "signals_found": ["api:fontcleaner"]},
        ])
        pd = _make_page_decisions({
            "content/docs.aspose.org/en/font/python/developer-guide/features.md":
                {"decision": "BODY_UPDATED", "body_hash_changed": True},
        })
        result = self._run_plan(pi, pd)
        assert result["pages_selected"] == 0

    def test_max_pages_limit_respected(self):
        pages_in = [
            {"path": f"content/docs.aspose.org/en/font/python/developer-guide/page{i}.md",
             "pia_score": "HIGH_IMPACT", "signals_found": ["api:fontcleaner"]}
            for i in range(20)
        ]
        pd_data = {
            p["path"]: {"decision": "EVIDENCE_ONLY", "body_hash_changed": False}
            for p in pages_in
        }
        result = self._run_plan(_make_page_impact(pages_in), _make_page_decisions(pd_data), max_pages=5)
        assert result["pages_selected"] == 5


# ─── CLI tests ────────────────────────────────────────────────────────────────

class TestPlannerCLI:

    def test_cli_exit_0_on_actionable_plan(self, tmp_path):
        pi = tmp_path / "page_impact.json"
        pd = tmp_path / "page_decisions.json"
        sd = tmp_path / "source_delta.json"
        kd = tmp_path / "knowledge_delta.json"
        out = tmp_path / "plan.json"

        _write_json(pi, _make_page_impact([
            {"path": "content/docs.aspose.org/en/font/python/developer-guide/features.md",
             "pia_score": "HIGH_IMPACT", "signals_found": ["api:fontcleaner"]}
        ]))
        _write_json(pd, _make_page_decisions({
            "content/docs.aspose.org/en/font/python/developer-guide/features.md":
                {"decision": "EVIDENCE_ONLY", "body_hash_changed": False}
        }))
        _write_json(sd, _make_source_delta())
        _write_json(kd, _make_knowledge_delta())

        exit_code = main([
            "font", "python",
            "--page-impact", str(pi),
            "--page-decisions", str(pd),
            "--source-delta", str(sd),
            "--knowledge-delta", str(kd),
            "--out", str(out),
        ])
        assert exit_code == 0
        data = json.loads(out.read_text())
        assert data["overall_status"] == "BODY_UPDATES_PLANNED"
        assert data["actionable_count"] == 1

    def test_cli_exit_1_on_missing_page_impact(self, tmp_path):
        pd = tmp_path / "page_decisions.json"
        _write_json(pd, _make_page_decisions({}))
        exit_code = main([
            "font", "python",
            "--page-impact", str(tmp_path / "nonexistent.json"),
            "--page-decisions", str(pd),
            "--out", str(tmp_path / "plan.json"),
        ])
        assert exit_code == 1

    def test_cli_exit_2_on_no_impacted_pages(self, tmp_path):
        pi = tmp_path / "page_impact.json"
        pd = tmp_path / "page_decisions.json"
        out = tmp_path / "plan.json"
        _write_json(pi, _make_page_impact([]))
        _write_json(pd, _make_page_decisions({}))
        exit_code = main([
            "font", "python",
            "--page-impact", str(pi),
            "--page-decisions", str(pd),
            "--out", str(out),
        ])
        assert exit_code == 2
