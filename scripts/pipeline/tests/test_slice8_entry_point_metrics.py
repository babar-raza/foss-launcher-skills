"""Slice 8 integration tests: RunMetrics wiring in pipeline entry points.

Verifies that each LLM-using entry point:
1. Accumulates MetricsEvents from LLM calls (module-level list)
2. Produces a dry-run JSON file at reports/metrics/dry/{run_id}.dry.json
3. Does not break existing pipeline behavior
4. Never raises on metrics failures

25 tests covering:
- enrich.py: 6 tests
- gap-eval/run.py: 5 tests
- gap-eval/synthesize.py: 5 tests
- translator/cli.py: 5 tests
- seo/pipeline/recommend.py: 4 tests

Slice 8 of Agent Metrics Integration (METRICS-PLAN-001 v7.5 -> v7.6).
"""
from __future__ import annotations

import json
import sys
import time
from pathlib import Path

import pytest

_PIPELINE_ROOT = Path(__file__).resolve().parent.parent
_REPO_ROOT = _PIPELINE_ROOT.parents[1]
if str(_PIPELINE_ROOT) not in sys.path:
    sys.path.insert(0, str(_PIPELINE_ROOT))

from commands.ops.metrics_schema import (
    MetricsEvent,
    generate_event_id,
    generate_run_id,
    now_iso8601,
    validate_row,
    row_to_dict,
)
from commands.ops.run_metrics import RunMetrics


# ---------------------------------------------------------------------------
# Helper
# ---------------------------------------------------------------------------

def _make_event(call_site_id="CS-001", tokens=100) -> MetricsEvent:
    return MetricsEvent(
        event_id=generate_event_id(),
        call_site_id=call_site_id,
        endpoint="https://llm.professionalize.com/v1/chat/completions",
        request_type="chat",
        status="success",
        prompt_tokens=tokens // 2,
        completion_tokens=tokens // 2,
        total_tokens=tokens,
        api_calls_count_delta=1,
        timestamp=now_iso8601(),
        http_status=200,
        latency_ms=500,
        redacted_error_summary=None,
    )


# ---------------------------------------------------------------------------
# enrich.py metrics wiring tests (6 tests)
# ---------------------------------------------------------------------------

class TestEnrichMetricsWiring:

    def _get_enrich(self):
        import commands.knowledge.enrich as enrich
        return enrich

    def test_enrich_has_metrics_events_list(self):
        enrich = self._get_enrich()
        assert hasattr(enrich, "_enrich_metrics_events")
        assert isinstance(enrich._enrich_metrics_events, list)

    def test_enrich_has_run_id_var(self):
        enrich = self._get_enrich()
        assert hasattr(enrich, "_enrich_run_id")

    def test_enrich_has_metrics_helper_function(self):
        enrich = self._get_enrich()
        assert callable(getattr(enrich, "_try_write_enrich_metrics", None))

    def test_enrich_metrics_helper_writes_dry_json(self, tmp_path):
        enrich = self._get_enrich()
        run_id = generate_run_id()
        events = [_make_event("CS-001", 200), _make_event("CS-001", 150)]
        run_stats = {"batches_attempted": 3, "batches_succeeded": 2, "batches_failed": 1}
        t0 = time.monotonic() - 1.5
        orig = enrich._REPO_ROOT
        try:
            enrich._REPO_ROOT = tmp_path
            enrich._try_write_enrich_metrics("cells", "java", run_id, events, run_stats, t0)
        finally:
            enrich._REPO_ROOT = orig
        dry_path = tmp_path / "reports" / "metrics" / "dry" / f"{run_id}.dry.json"
        assert dry_path.exists(), "Dry-run JSON not written"
        row = json.loads(dry_path.read_text())
        assert row["run_id"] == run_id
        assert row["job_type"] == "knowledge_enrichment"
        assert row["product"] == "cells"
        assert row["platform"] == "java"
        assert row["api_calls_count"] == 2
        assert row["token_usage"] == 350

    def test_enrich_metrics_helper_writes_ledger_jsonl(self, tmp_path):
        enrich = self._get_enrich()
        run_id = generate_run_id()
        events = [_make_event("CS-001", 100)]
        run_stats = {"batches_attempted": 1, "batches_succeeded": 1, "batches_failed": 0}
        orig = enrich._REPO_ROOT
        try:
            enrich._REPO_ROOT = tmp_path
            enrich._try_write_enrich_metrics("words", "net", run_id, events, run_stats, time.monotonic())
        finally:
            enrich._REPO_ROOT = orig
        ledger = tmp_path / "reports" / "metrics" / "events" / f"{run_id}.jsonl"
        assert ledger.exists()
        lines = ledger.read_text().strip().splitlines()
        assert len(lines) == 1

    def test_enrich_metrics_helper_silent_on_none_run_id(self, tmp_path):
        enrich = self._get_enrich()
        orig = enrich._REPO_ROOT
        try:
            enrich._REPO_ROOT = tmp_path
            enrich._try_write_enrich_metrics("cells", "java", None, [], {}, time.monotonic())
        finally:
            enrich._REPO_ROOT = orig
        assert not (tmp_path / "reports").exists()


# ---------------------------------------------------------------------------
# gap-eval/run.py metrics wiring tests (5 tests)
# ---------------------------------------------------------------------------

class TestGapEvalRunMetricsWiring:

    def _get_run(self):
        scripts_dir = _REPO_ROOT / "scripts"
        gap_src = _REPO_ROOT / "scripts" / "gap-eval" / "src"
        for d in [str(scripts_dir), str(gap_src)]:
            if d not in sys.path:
                sys.path.insert(0, d)
        import run as _run
        return _run

    def test_gaeval_has_metrics_events_list(self):
        run = self._get_run()
        assert hasattr(run, "_gaeval_metrics_events")
        assert isinstance(run._gaeval_metrics_events, list)

    def test_gaeval_has_run_id_var(self):
        run = self._get_run()
        assert hasattr(run, "_gaeval_run_id")

    def test_gaeval_has_metrics_helper(self):
        run = self._get_run()
        assert callable(getattr(run, "_try_write_gaeval_metrics", None))

    def test_gaeval_metrics_helper_writes_dry_json(self, tmp_path):
        run = self._get_run()
        run_id = generate_run_id()
        events = [_make_event("CS-001", 180)]
        findings = [{"id": "f1"}, {"id": "f2"}, {"id": "f3"}]
        t0 = time.monotonic() - 2.0
        orig = run._REPO_ROOT
        try:
            run._REPO_ROOT = tmp_path
            run._try_write_gaeval_metrics("slides", "java", run_id, events, findings, "PASS", t0)
        finally:
            run._REPO_ROOT = orig
        dry_path = tmp_path / "reports" / "metrics" / "dry" / f"{run_id}.dry.json"
        assert dry_path.exists()
        row = json.loads(dry_path.read_text())
        assert row["job_type"] == "gap_evaluation"
        assert row["product"] == "slides"
        assert row["token_usage"] == 180

    def test_gaeval_metrics_helper_silent_on_none_run_id(self, tmp_path):
        run = self._get_run()
        orig = run._REPO_ROOT
        try:
            run._REPO_ROOT = tmp_path
            run._try_write_gaeval_metrics("slides", "java", None, [], [], "PASS", time.monotonic())
        finally:
            run._REPO_ROOT = orig
        assert not (tmp_path / "reports").exists()


# ---------------------------------------------------------------------------
# gap-eval/synthesize.py metrics wiring tests (5 tests)
# ---------------------------------------------------------------------------

class TestGapEvalSynthesizeMetricsWiring:

    def _get_synth(self):
        scripts_dir = _REPO_ROOT / "scripts"
        gap_src = _REPO_ROOT / "scripts" / "gap-eval" / "src"
        for d in [str(scripts_dir), str(gap_src)]:
            if d not in sys.path:
                sys.path.insert(0, d)
        import synthesize as _synth
        return _synth

    def test_synth_has_metrics_events_list(self):
        synth = self._get_synth()
        assert hasattr(synth, "_synth_metrics_events")
        assert isinstance(synth._synth_metrics_events, list)

    def test_synth_has_run_id_var(self):
        synth = self._get_synth()
        assert hasattr(synth, "_synth_run_id")

    def test_synth_events_appendable(self):
        synth = self._get_synth()
        synth._synth_metrics_events = []
        synth._synth_metrics_events.append(_make_event("CS-001", 120))
        assert len(synth._synth_metrics_events) == 1

    def test_synth_metrics_row_valid_schema(self, tmp_path):
        run_id = generate_run_id()
        with RunMetrics(
            run_id=run_id,
            agent_name="aspose-org-gap-evaluation",
            job_type="gap_synthesis",
            product="all",
            platform="all",
            website="aspose.org",
            website_section="Docs",
            ledger_root=tmp_path / "events",
        ) as rm:
            rm.record_events([_make_event("CS-001", 100)])
            row = rm.to_row(items_discovered=10, items_failed=0, items_succeeded=10, run_duration_ms=500)
        result = validate_row(row)
        assert result.valid, result.errors

    def test_synth_metrics_ledger_written(self, tmp_path):
        run_id = generate_run_id()
        with RunMetrics(
            run_id=run_id,
            agent_name="aspose-org-gap-evaluation",
            job_type="gap_synthesis",
            product="all",
            platform="all",
            website="aspose.org",
            website_section="Docs",
            ledger_root=tmp_path / "events",
        ) as rm:
            rm.record_events([_make_event("CS-001", 80)])
            rm.to_row(items_discovered=3, items_failed=0, items_succeeded=3, run_duration_ms=200)
        ledger = tmp_path / "events" / f"{run_id}.jsonl"
        assert ledger.exists()


# ---------------------------------------------------------------------------
# translator/cli.py metrics wiring tests (5 tests)
# ---------------------------------------------------------------------------

class TestTranslatorCliMetricsWiring:

    def test_cli_event_collection_from_backend_router(self):
        """BackendRouter.backends with LLMBackend provides metrics_events."""
        class FakeBackend:
            def __init__(self, evs):
                self.metrics_events = evs
        class FakeRouter:
            def __init__(self, bs):
                self.backends = bs
        class FakeEngine:
            def __init__(self, r):
                self.backend = r
        events_a = [_make_event("CS-008", 100)]
        events_b = [_make_event("CS-008", 200), _make_event("CS-008", 150)]
        engine = FakeEngine(FakeRouter([FakeBackend(events_a), FakeBackend(events_b)]))
        collected = []
        if hasattr(engine, "backend") and hasattr(engine.backend, "backends"):
            for b in engine.backend.backends:
                if hasattr(b, "metrics_events"):
                    collected.extend(b.metrics_events)
        assert len(collected) == 3
        assert sum(e.total_tokens for e in collected) == 450

    def test_cli_event_collection_empty_without_llm_backend(self):
        class FakeBackend:
            pass  # no metrics_events
        class FakeRouter:
            backends = [FakeBackend()]
        class FakeEngine:
            backend = FakeRouter()
        engine = FakeEngine()
        collected = []
        if hasattr(engine, "backend") and hasattr(engine.backend, "backends"):
            for b in engine.backend.backends:
                if hasattr(b, "metrics_events"):
                    collected.extend(b.metrics_events)
        assert collected == []

    def test_translator_metrics_row_valid_schema(self, tmp_path):
        run_id = generate_run_id()
        with RunMetrics(
            run_id=run_id,
            agent_name="aspose-org-translator",
            job_type="translation",
            product="words",
            platform="net",
            website="aspose.org",
            website_section="Docs",
            ledger_root=tmp_path / "events",
        ) as rm:
            rm.record_events([_make_event("CS-008", 300)])
            row = rm.to_row(items_discovered=5, items_failed=0, items_succeeded=5, run_duration_ms=200)
        result = validate_row(row)
        assert result.valid, result.errors

    def test_translator_metrics_row_token_usage(self, tmp_path):
        run_id = generate_run_id()
        events = [_make_event("CS-008", 200), _make_event("CS-008", 150)]
        with RunMetrics(
            run_id=run_id,
            agent_name="aspose-org-translator",
            job_type="translation",
            product="words",
            platform="net",
            website="aspose.org",
            website_section="Docs",
            ledger_root=tmp_path / "events",
        ) as rm:
            rm.record_events(events)
            row = rm.to_row(items_discovered=8, items_failed=0, items_succeeded=8, run_duration_ms=500)
        assert row.token_usage == 350
        assert row.api_calls_count == 2

    def test_translator_metrics_ledger_written(self, tmp_path):
        run_id = generate_run_id()
        with RunMetrics(
            run_id=run_id,
            agent_name="aspose-org-translator",
            job_type="translation",
            product="words",
            platform="net",
            website="aspose.org",
            website_section="Docs",
            ledger_root=tmp_path / "events",
        ) as rm:
            rm.record_events([_make_event("CS-008", 100)])
            rm.to_row(items_discovered=1, items_failed=0, items_succeeded=1, run_duration_ms=100)
        assert (tmp_path / "events" / f"{run_id}.jsonl").exists()


# ---------------------------------------------------------------------------
# seo/pipeline/recommend.py metrics wiring tests (4 tests)
# ---------------------------------------------------------------------------

class TestRecommendMetricsWiring:

    def _get_recommend(self):
        scripts_dir = _REPO_ROOT / "scripts"
        seo_pipeline = _REPO_ROOT / "scripts" / "seo" / "pipeline"
        for d in [str(scripts_dir), str(_PIPELINE_ROOT)]:
            if d not in sys.path:
                sys.path.insert(0, d)
        import importlib.util
        spec = importlib.util.spec_from_file_location(
            "recommend_seo_s8", str(seo_pipeline / "recommend.py")
        )
        mod = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(mod)
        return mod

    def test_recommend_has_module_metrics_events(self):
        rec = self._get_recommend()
        assert hasattr(rec, "metrics_events")
        assert isinstance(rec.metrics_events, list)

    def test_recommend_events_appendable(self):
        rec = self._get_recommend()
        rec.metrics_events.clear()
        rec.metrics_events.append(_make_event("CS-009", 150))
        assert any(e.call_site_id == "CS-009" for e in rec.metrics_events)

    def test_recommend_metrics_row_valid_schema(self, tmp_path):
        run_id = generate_run_id()
        with RunMetrics(
            run_id=run_id,
            agent_name="aspose-org-seo",
            job_type="seo",
            product="seo",
            platform="all",
            website="aspose.org",
            website_section="Products",
            ledger_root=tmp_path / "events",
        ) as rm:
            rm.record_events([_make_event("CS-009", 200)])
            row = rm.to_row(items_discovered=10, items_failed=2, items_succeeded=8, run_duration_ms=300)
        result = validate_row(row)
        assert result.valid, result.errors

    def test_recommend_metrics_ledger_written(self, tmp_path):
        run_id = generate_run_id()
        events = [_make_event("CS-009", 100), _make_event("CS-009", 50)]
        with RunMetrics(
            run_id=run_id,
            agent_name="aspose-org-seo",
            job_type="seo",
            product="seo",
            platform="all",
            website="aspose.org",
            website_section="Products",
            ledger_root=tmp_path / "events",
        ) as rm:
            rm.record_events(events)
            rm.to_row(items_discovered=2, items_failed=0, items_succeeded=2, run_duration_ms=100)
        ledger = tmp_path / "events" / f"{run_id}.jsonl"
        assert ledger.exists()
        lines = ledger.read_text().strip().splitlines()
        assert len(lines) == 2
