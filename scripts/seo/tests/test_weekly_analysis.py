"""SEO-INREPO-ANALYSIS-WORKFLOW: weekly_analysis.py orchestrator tests.

"Noteworthy" (exit 1) must stay narrow -- only a NEW duplicate-title group
or a NEW investigate-worthy keyword gap should trigger it. Already-known,
already-tracked backlogs (title WARN count, KB keyword-count gaps) must
stay informational-only, never triggering the issue-only workflow on their
own -- otherwise it would fire every week for debt this mission already
knows about and is working down via its own governed process.
"""
from __future__ import annotations

import sys
from pathlib import Path

import pytest

_SCRIPTS = Path(__file__).resolve().parents[2]
_PIPELINE = _SCRIPTS / "pipeline"
_CI_CHECKS = _SCRIPTS / "ci" / "checks"
if str(_SCRIPTS) not in sys.path:
    sys.path.insert(0, str(_SCRIPTS))
if str(_PIPELINE) not in sys.path:
    sys.path.insert(0, str(_PIPELINE))
if str(_CI_CHECKS) not in sys.path:
    sys.path.insert(0, str(_CI_CHECKS))

import seo.pipeline.weekly_analysis as weekly  # noqa: E402


def test_run_not_noteworthy_when_everything_clean(monkeypatch):
    monkeypatch.setattr(weekly.check_duplicate_titles, "find_duplicate_titles", lambda: {})
    monkeypatch.setattr(weekly.check_duplicate_titles, "load_baseline", lambda: {})
    monkeypatch.setattr(weekly.keyword_gap_report, "build_gap_report", lambda: {
        "meta": {"investigate_count": 0, "structural_count": 2}, "investigate": [], "structural": [],
    })
    monkeypatch.setattr(weekly.frontmatter_grounding_audit, "build_report", lambda: {
        "meta": {"total_kb_pages": 10, "by_grounded_source": {"derived": 10}, "pages_meeting_min_5_count": 3},
    })
    monkeypatch.setattr(weekly.title_consistency_evaluator, "build_report", lambda: {
        "meta": {"total_evaluated": 62, "warn_count": 62, "pass_count": 0,
                 "docs_devguide_index_total": 31, "docs_devguide_index_warn": 31,
                 "kb_faq_total": 31, "kb_faq_warn": 31},
    })

    summary = weekly.run()
    assert summary["noteworthy"] is False
    assert summary["errors"] == []


def test_run_noteworthy_on_new_duplicate_title_group(monkeypatch):
    monkeypatch.setattr(weekly.check_duplicate_titles, "find_duplicate_titles",
                         lambda: {"docs.aspose.org::New Dup": ["a.md", "b.md"]})
    monkeypatch.setattr(weekly.check_duplicate_titles, "load_baseline", lambda: {})
    monkeypatch.setattr(weekly.keyword_gap_report, "build_gap_report", lambda: {
        "meta": {"investigate_count": 0, "structural_count": 0}, "investigate": [], "structural": [],
    })
    monkeypatch.setattr(weekly.frontmatter_grounding_audit, "build_report", lambda: {
        "meta": {"total_kb_pages": 0, "by_grounded_source": {}, "pages_meeting_min_5_count": 0},
    })
    monkeypatch.setattr(weekly.title_consistency_evaluator, "build_report", lambda: {
        "meta": {"total_evaluated": 0, "warn_count": 0, "pass_count": 0,
                 "docs_devguide_index_total": 0, "docs_devguide_index_warn": 0,
                 "kb_faq_total": 0, "kb_faq_warn": 0},
    })

    summary = weekly.run()
    assert summary["noteworthy"] is True
    assert summary["stages"]["duplicate_titles"]["new_group_count"] == 1


def test_run_noteworthy_on_investigate_worthy_gap(monkeypatch):
    monkeypatch.setattr(weekly.check_duplicate_titles, "find_duplicate_titles", lambda: {})
    monkeypatch.setattr(weekly.check_duplicate_titles, "load_baseline", lambda: {})
    monkeypatch.setattr(weekly.keyword_gap_report, "build_gap_report", lambda: {
        "meta": {"investigate_count": 1, "structural_count": 0},
        "investigate": [{"gsc_url": "https://docs.aspose.org/pdf/net/gone/", "total_impressions": 20}],
        "structural": [],
    })
    monkeypatch.setattr(weekly.frontmatter_grounding_audit, "build_report", lambda: {
        "meta": {"total_kb_pages": 0, "by_grounded_source": {}, "pages_meeting_min_5_count": 0},
    })
    monkeypatch.setattr(weekly.title_consistency_evaluator, "build_report", lambda: {
        "meta": {"total_evaluated": 0, "warn_count": 0, "pass_count": 0,
                 "docs_devguide_index_total": 0, "docs_devguide_index_warn": 0,
                 "kb_faq_total": 0, "kb_faq_warn": 0},
    })

    summary = weekly.run()
    assert summary["noteworthy"] is True
    assert summary["stages"]["keyword_gaps"]["investigate_count"] == 1


def test_known_title_backlog_alone_is_not_noteworthy(monkeypatch):
    """The already-known, already-tracked 62-page title WARN backlog must
    NOT by itself make this workflow noteworthy -- it's tracked via the
    frozen pilot process, not this weekly check."""
    monkeypatch.setattr(weekly.check_duplicate_titles, "find_duplicate_titles", lambda: {})
    monkeypatch.setattr(weekly.check_duplicate_titles, "load_baseline", lambda: {})
    monkeypatch.setattr(weekly.keyword_gap_report, "build_gap_report", lambda: {
        "meta": {"investigate_count": 0, "structural_count": 0}, "investigate": [], "structural": [],
    })
    monkeypatch.setattr(weekly.frontmatter_grounding_audit, "build_report", lambda: {
        "meta": {"total_kb_pages": 309, "by_grounded_source": {"derived": 295, "gsc": 12, "none": 2},
                 "pages_meeting_min_5_count": 84},
    })
    monkeypatch.setattr(weekly.title_consistency_evaluator, "build_report", lambda: {
        "meta": {"total_evaluated": 62, "warn_count": 62, "pass_count": 0,
                 "docs_devguide_index_total": 31, "docs_devguide_index_warn": 31,
                 "kb_faq_total": 31, "kb_faq_warn": 31},
    })

    summary = weekly.run()
    assert summary["noteworthy"] is False


def test_run_records_error_and_sets_noteworthy_when_a_stage_raises(monkeypatch):
    def _raise():
        raise RuntimeError("simulated stage failure")
    monkeypatch.setattr(weekly.check_duplicate_titles, "find_duplicate_titles", _raise)
    monkeypatch.setattr(weekly.keyword_gap_report, "build_gap_report", lambda: {
        "meta": {"investigate_count": 0, "structural_count": 0}, "investigate": [], "structural": [],
    })
    monkeypatch.setattr(weekly.frontmatter_grounding_audit, "build_report", lambda: {
        "meta": {"total_kb_pages": 0, "by_grounded_source": {}, "pages_meeting_min_5_count": 0},
    })
    monkeypatch.setattr(weekly.title_consistency_evaluator, "build_report", lambda: {
        "meta": {"total_evaluated": 0, "warn_count": 0, "pass_count": 0,
                 "docs_devguide_index_total": 0, "docs_devguide_index_warn": 0,
                 "kb_faq_total": 0, "kb_faq_warn": 0},
    })

    summary = weekly.run()
    assert len(summary["errors"]) == 1
    assert "duplicate_titles" in summary["errors"][0]


def test_main_exit_code_2_on_stage_error(monkeypatch, tmp_path):
    monkeypatch.setattr(weekly, "REPORTS_DIR", tmp_path)
    def _raise():
        raise RuntimeError("boom")
    monkeypatch.setattr(weekly.check_duplicate_titles, "find_duplicate_titles", _raise)
    monkeypatch.setattr(weekly.keyword_gap_report, "build_gap_report", lambda: {
        "meta": {"investigate_count": 0, "structural_count": 0}, "investigate": [], "structural": [],
    })
    monkeypatch.setattr(weekly.frontmatter_grounding_audit, "build_report", lambda: {
        "meta": {"total_kb_pages": 0, "by_grounded_source": {}, "pages_meeting_min_5_count": 0},
    })
    monkeypatch.setattr(weekly.title_consistency_evaluator, "build_report", lambda: {
        "meta": {"total_evaluated": 0, "warn_count": 0, "pass_count": 0,
                 "docs_devguide_index_total": 0, "docs_devguide_index_warn": 0,
                 "kb_faq_total": 0, "kb_faq_warn": 0},
    })
    assert weekly.main() == 2


def test_main_exit_code_0_when_clean(monkeypatch, tmp_path):
    monkeypatch.setattr(weekly, "REPORTS_DIR", tmp_path)
    monkeypatch.setattr(weekly.check_duplicate_titles, "find_duplicate_titles", lambda: {})
    monkeypatch.setattr(weekly.check_duplicate_titles, "load_baseline", lambda: {})
    monkeypatch.setattr(weekly.keyword_gap_report, "build_gap_report", lambda: {
        "meta": {"investigate_count": 0, "structural_count": 0}, "investigate": [], "structural": [],
    })
    monkeypatch.setattr(weekly.frontmatter_grounding_audit, "build_report", lambda: {
        "meta": {"total_kb_pages": 0, "by_grounded_source": {}, "pages_meeting_min_5_count": 0},
    })
    monkeypatch.setattr(weekly.title_consistency_evaluator, "build_report", lambda: {
        "meta": {"total_evaluated": 0, "warn_count": 0, "pass_count": 0,
                 "docs_devguide_index_total": 0, "docs_devguide_index_warn": 0,
                 "kb_faq_total": 0, "kb_faq_warn": 0},
    })
    assert weekly.main() == 0
    assert (tmp_path / "weekly_analysis_summary.json").exists()
    assert (tmp_path / "weekly_analysis_summary.md").exists()
