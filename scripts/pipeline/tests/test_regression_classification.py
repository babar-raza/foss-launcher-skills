"""Tests for regression_classification.py (HARDEN-A10 — S-114 as real code).

Covers: grade-rank ordering, deterministic evidence-citation intersection,
consumer_usefulness-only detection, the classify_page decision tree (JUSTIFIED /
UNJUSTIFIED_CANDIDATE / LLM-judged / NEEDS_HUMAN_REVIEW), and — the actual
completeness guarantee this script exists to enforce in code — that main()
refuses to write a partial/duplicated output.
"""
from __future__ import annotations

import json
import sys
from pathlib import Path

import pytest

_PIPELINE_DIR = Path(__file__).resolve().parent.parent
if str(_PIPELINE_DIR) not in sys.path:
    sys.path.insert(0, str(_PIPELINE_DIR))

import commands.governance.regression_classification as rc  # noqa: E402


# ---------------------------------------------------------------------------
# Pure helpers
# ---------------------------------------------------------------------------

def test_grade_rank_ordering():
    assert rc._grade_rank("A") > rc._grade_rank("B") > rc._grade_rank("C")
    assert rc._grade_rank("C") > rc._grade_rank("D") > rc._grade_rank("F")
    assert rc._grade_rank(None) is None
    assert rc._grade_rank("") is None


def test_deterministic_citation_finds_removed_api_overlap():
    evidence = {"apis": ["Scene.from_file", "Scene.save"], "claims": []}
    delta = {"removed_apis": ["Scene.save"], "modified_apis": [], "removed_claims": [], "modified_claims": []}
    hits = rc._deterministic_citation(evidence, delta)
    assert hits == ["Scene.save"]


def test_deterministic_citation_finds_claim_overlap():
    evidence = {"apis": [], "claims": ["CLM-001", "CLM-002"]}
    delta = {"removed_claims": ["CLM-002"], "modified_claims": [], "removed_apis": [], "modified_apis": []}
    hits = rc._deterministic_citation(evidence, delta)
    assert hits == ["CLM-002"]


def test_deterministic_citation_empty_when_no_overlap():
    evidence = {"apis": ["Foo.bar"], "claims": ["CLM-999"]}
    delta = {"removed_apis": ["Other.thing"], "modified_apis": [], "removed_claims": [], "modified_claims": []}
    assert rc._deterministic_citation(evidence, delta) == []


def test_deterministic_citation_handles_missing_delta_keys():
    """Older-style knowledge_delta.json entries omit claims/apis arrays entirely
    (RPR-A-01 research confirmed 2 real products have this shape) — must not crash."""
    assert rc._deterministic_citation({"apis": ["X"]}, {"reason": "member-doc enrichment"}) == []


def test_consumer_usefulness_only_detection():
    assert rc._is_consumer_usefulness_only(
        ["2 WARN finding(s) [consumer_usefulness×2] -> base grade A",
         "US ceiling applied (WARN) -> grade capped at B"]
    ) is True
    assert rc._is_consumer_usefulness_only(
        ["1 FAIL finding(s) [type_accuracy×1] -> base grade D"]
    ) is False
    assert rc._is_consumer_usefulness_only([]) is False


# ---------------------------------------------------------------------------
# classify_page decision tree
# ---------------------------------------------------------------------------

class TestClassifyPage:
    def test_justified_when_citation_found(self, tmp_path):
        page = tmp_path / "page.md"
        page.write_text(
            "---\nevidence:\n  apis: [Old.Method]\n  claims: []\n---\nbody\n",
            encoding="utf-8",
        )
        delta = {"removed_apis": ["Old.Method"]}
        row = rc.classify_page(page, "fam", "plat", "A", "C", ["1 FAIL"], delta)
        assert row["classification"] == "JUSTIFIED"
        assert "Old.Method" in row["rationale"]
        assert row["remediation_priority"] == "NONE"

    def test_unjustified_candidate_when_consumer_usefulness_only(self, tmp_path):
        page = tmp_path / "page.md"
        page.write_text("---\nevidence:\n  apis: []\n  claims: []\n---\nbody\n", encoding="utf-8")
        reasons = ["3 WARN finding(s) [consumer_usefulness×3] -> base grade C"]
        row = rc.classify_page(page, "fam", "plat", "A", "C", reasons, {})
        assert row["classification"] == "UNJUSTIFIED_CANDIDATE"
        assert row["remediation_priority"] == "NORMAL"

    def test_needs_human_review_with_no_llm_judge(self, tmp_path):
        page = tmp_path / "page.md"
        page.write_text("---\nevidence:\n  apis: []\n  claims: []\n---\nbody\n", encoding="utf-8")
        reasons = ["1 FAIL finding(s) [type_accuracy×1] -> base grade D"]
        row = rc.classify_page(page, "fam", "plat", "A", "D", reasons, {})
        assert row["classification"] == "NEEDS_HUMAN_REVIEW"
        assert row["remediation_priority"] == "HIGH"

    def test_llm_judge_used_when_deterministic_check_inconclusive(self, tmp_path):
        page = tmp_path / "page.md"
        page.write_text("---\nevidence:\n  apis: []\n  claims: []\n---\nbody\n", encoding="utf-8")
        reasons = ["1 FAIL finding(s) [type_accuracy×1] -> base grade D"]

        def fake_judge(**kwargs):
            return {
                "classification": "UNJUSTIFIED",
                "rationale": "the removed method is still documented in prose",
                "citation": "line 42: 'Call Old.Method() to convert'",
                "remediation_priority": "HIGH",
                "remediation_route": "re-run body-refresh",
            }

        row = rc.classify_page(page, "fam", "plat", "A", "D", reasons, {}, llm_judge=fake_judge)
        assert row["classification"] == "UNJUSTIFIED"
        assert "cites:" in row["rationale"]

    def test_llm_judge_without_citation_escalates_not_guesses(self, tmp_path):
        """An LLM judgment with no citation must NOT be trusted — escalate instead
        of silently accepting an uncited verdict."""
        page = tmp_path / "page.md"
        page.write_text("---\nevidence:\n  apis: []\n  claims: []\n---\nbody\n", encoding="utf-8")
        reasons = ["1 FAIL finding(s) [type_accuracy×1] -> base grade D"]

        def uncited_judge(**kwargs):
            return {"classification": "UNJUSTIFIED", "rationale": "seems wrong", "citation": ""}

        row = rc.classify_page(page, "fam", "plat", "A", "D", reasons, {}, llm_judge=uncited_judge)
        assert row["classification"] == "NEEDS_HUMAN_REVIEW"


# ---------------------------------------------------------------------------
# run() / completeness guarantee
# ---------------------------------------------------------------------------

class TestRunAndCompleteness:
    def test_run_skips_non_regressions(self, tmp_path, monkeypatch):
        """A page whose grade improved or stayed the same must not appear."""
        page_a = tmp_path / "content" / "docs.aspose.org" / "en" / "fam" / "plat" / "a.md"
        page_a.parent.mkdir(parents=True)
        page_a.write_text("---\ngrade: A\ngrade_reasons: []\nevidence:\n  apis: []\n---\nbody\n",
                          encoding="utf-8")

        monkeypatch.setattr(rc, "discover_content", lambda family, platform, skip_drafts=True: [page_a])
        monkeypatch.setattr(rc, "_grade_from_ref", lambda path, ref: ("A", []))  # unchanged
        monkeypatch.setattr(rc, "_load_knowledge_delta", lambda f, p: {})
        monkeypatch.setattr(rc, "_resolve_baseline_ref", lambda ref, root: True)

        report = rc.run("fam", "plat", repo_root=tmp_path)
        assert report["regressions_found"] == 0
        assert report["items"] == []

    def test_run_finds_regression_and_classifies_it(self, tmp_path, monkeypatch):
        page_a = tmp_path / "content" / "docs.aspose.org" / "en" / "fam" / "plat" / "a.md"
        page_a.parent.mkdir(parents=True)
        page_a.write_text(
            '---\ngrade: C\ngrade_reasons:\n  - "3 WARN finding(s) [consumer_usefulness x3] -> base grade C"\n'
            "evidence:\n  apis: []\n  claims: []\n---\nbody\n",
            encoding="utf-8",
        )
        monkeypatch.setattr(rc, "discover_content", lambda family, platform, skip_drafts=True: [page_a])
        monkeypatch.setattr(rc, "_grade_from_ref", lambda path, ref: ("A", []))
        monkeypatch.setattr(rc, "_load_knowledge_delta", lambda f, p: {})
        monkeypatch.setattr(rc, "_resolve_baseline_ref", lambda ref, root: True)

        report = rc.run("fam", "plat", repo_root=tmp_path)
        assert report["regressions_found"] == 1
        assert report["items"][0]["classification"] == "UNJUSTIFIED_CANDIDATE"
        assert report["items"][0]["prior_grade"] == "A"
        assert report["items"][0]["current_grade"] == "C"

    def test_main_refuses_to_write_on_count_mismatch(self, tmp_path, monkeypatch, capsys):
        """Simulates the exact defect class this script exists to prevent: a
        classifier that silently drops or duplicates an item."""
        fake_report = {
            "family": "fam", "platform": "plat", "baseline_ref": "origin/main",
            "generated_at": "2026-07-22T00:00:00Z",
            "pages_scanned": 5, "regressions_found": 3,  # claims 3...
            "items": [{"path": "a.md", "classification": "JUSTIFIED",
                      "citation_grade_reasons": [], "rationale": "", "prior_grade": "A",
                      "current_grade": "B", "family": "fam", "platform": "plat", "site": "docs",
                      "remediation_priority": "NONE", "remediation_route": "none"}],  # ...but only 1 item
        }
        monkeypatch.setattr(rc, "run", lambda *a, **k: fake_report)
        rc_dir = tmp_path / "reports" / "regression_classification"
        monkeypatch.setattr(rc, "_REPO_ROOT", tmp_path)

        exit_code = rc.main(["fam", "plat"])
        assert exit_code == 1
        err = capsys.readouterr().err
        assert "COMPLETENESS_VIOLATION" in err
        assert not rc_dir.exists() or not list(rc_dir.glob("*.json"))

    def test_ungradeable_current_page_is_flagged_not_silently_skipped(self, tmp_path, monkeypatch):
        """R1: a page graded at baseline but with NO readable grade now (missing
        or corrupted grade: frontmatter — the wave3_locale_incident corruption
        class) must surface as UNGRADEABLE_REGRESSION, not disappear silently.
        Before the fix, this made regressions_found and len(items) shrink
        together, defeating the completeness check entirely."""
        page = tmp_path / "content" / "docs.aspose.org" / "en" / "fam" / "plat" / "a.md"
        page.parent.mkdir(parents=True)
        page.write_text("---\ntitle: no grade field at all\n---\nbody\n", encoding="utf-8")

        monkeypatch.setattr(rc, "discover_content", lambda family, platform, skip_drafts=True: [page])
        monkeypatch.setattr(rc, "_grade_from_ref", lambda path, ref: ("A", []))  # was A at baseline
        monkeypatch.setattr(rc, "_load_knowledge_delta", lambda f, p: {})
        monkeypatch.setattr(rc, "_resolve_baseline_ref", lambda ref, root: True)

        report = rc.run("fam", "plat", repo_root=tmp_path)
        assert report["regressions_found"] == 1
        assert len(report["items"]) == 1
        assert report["items"][0]["classification"] == "UNGRADEABLE_REGRESSION"
        assert report["items"][0]["prior_grade"] == "A"
        assert report["items"][0]["current_grade"] is None

    def test_invalid_baseline_ref_raises_not_silently_zero(self, tmp_path, monkeypatch):
        """R2: a baseline ref that doesn't resolve (typo, rewritten history) must
        raise, not silently produce the same 'zero regressions' output as a
        genuinely clean baseline — those two outcomes were indistinguishable
        before this fix."""
        monkeypatch.setattr(rc, "_resolve_baseline_ref", lambda ref, root: False)
        with pytest.raises(ValueError, match="does not resolve"):
            rc.run("fam", "plat", baseline_ref="totally-bogus-ref", repo_root=tmp_path)

    def test_main_exits_2_on_invalid_baseline_ref(self, tmp_path, monkeypatch, capsys):
        monkeypatch.setattr(rc, "_resolve_baseline_ref", lambda ref, root: False)
        exit_code = rc.main(["fam", "plat", "--baseline-ref", "totally-bogus-ref"])
        assert exit_code == 2
        assert "ERROR" in capsys.readouterr().err

    def test_valid_baseline_ref_smoke(self, monkeypatch):
        """_resolve_baseline_ref itself, against this real repo's own HEAD."""
        assert rc._resolve_baseline_ref("HEAD", rc._REPO_ROOT) is True
        assert rc._resolve_baseline_ref("definitely-not-a-real-ref-xyz", rc._REPO_ROOT) is False

    def test_main_writes_complete_report(self, tmp_path, monkeypatch, capsys):
        fake_report = {
            "family": "fam", "platform": "plat", "baseline_ref": "origin/main",
            "generated_at": "2026-07-22T00-00-00Z",
            "pages_scanned": 2, "regressions_found": 1,
            "items": [{"path": "a.md", "classification": "JUSTIFIED",
                      "citation_grade_reasons": [], "rationale": "x", "prior_grade": "A",
                      "current_grade": "B", "family": "fam", "platform": "plat", "site": "docs",
                      "remediation_priority": "NONE", "remediation_route": "none"}],
        }
        monkeypatch.setattr(rc, "run", lambda *a, **k: fake_report)
        monkeypatch.setattr(rc, "_REPO_ROOT", tmp_path)

        exit_code = rc.main(["fam", "plat", "--run-id", "test-run"])
        assert exit_code == 0
        out_path = tmp_path / "reports" / "regression_classification" / "test-run.json"
        assert out_path.is_file()
        written = json.loads(out_path.read_text(encoding="utf-8"))
        assert len(written["items"]) == 1
        assert written["regressions_found"] == 1
