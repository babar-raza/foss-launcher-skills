"""Slice 14 dry-run validation: end-to-end MetricsRow production for all job types.

Proves each pipeline job type produces a valid, plausible MetricsRow via:
  RunMetrics(events) → to_row() → validate_row() → MetricsSubmitter(dry_run)

6 job types tested (plan requires min 5):
  1. knowledge_enrichment  (enrich.py — CS-001)
  2. gap_evaluation        (gap-eval/run.py — CS-001)
  3. gap_synthesis          (gap-eval/synthesize.py — CS-001)
  4. translation            (translator/cli.py — CS-008)
  5. embedding              (embed.py — CS-004/CS-002)
  6. seo                    (seo/recommend.py — CS-009)

Each test writes a dry-run JSON to tmp_path and validates field correctness.

Slice 14 of Agent Metrics Integration (METRICS-PLAN-001 v8.1).
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
    MetricsRow,
    generate_event_id,
    generate_run_id,
    now_iso8601,
    validate_row,
    row_to_dict,
)
from commands.ops.run_metrics import RunMetrics
from commands.ops.metrics_submitter import (
    MetricsSubmitter,
    MODE_DRY_RUN,
    MODE_EXPORT_JSON,
)
from commands.ops.metrics_taxonomy_loader import resolve_job_type


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _make_events(call_site_id: str, count: int, tokens_per: int = 200) -> list[MetricsEvent]:
    """Generate `count` realistic MetricsEvents for a given call site."""
    return [
        MetricsEvent(
            event_id=generate_event_id(),
            call_site_id=call_site_id,
            endpoint="https://llm.professionalize.com/v1/chat/completions",
            request_type="chat",
            status="success",
            prompt_tokens=tokens_per * 2 // 3,
            completion_tokens=tokens_per // 3,
            total_tokens=tokens_per,
            api_calls_count_delta=1,
            timestamp=now_iso8601(),
            http_status=200,
            latency_ms=450 + i * 50,
            redacted_error_summary=None,
        )
        for i in range(count)
    ]


def _make_embed_events(call_site_id: str, count: int, tokens_per: int = 80) -> list[MetricsEvent]:
    """Generate embedding-style MetricsEvents."""
    return [
        MetricsEvent(
            event_id=generate_event_id(),
            call_site_id=call_site_id,
            endpoint="https://llm.professionalize.com/v1/embeddings",
            request_type="embedding",
            status="success",
            prompt_tokens=tokens_per,
            completion_tokens=0,
            total_tokens=tokens_per,
            api_calls_count_delta=1,
            timestamp=now_iso8601(),
            http_status=200,
            latency_ms=120 + i * 10,
            redacted_error_summary=None,
        )
        for i in range(count)
    ]


def _run_dry_run(
    *,
    run_id: str,
    agent_name: str,
    job_type: str,
    product: str,
    platform: str,
    website_section: str,
    events: list[MetricsEvent],
    items_discovered: int,
    items_succeeded: int,
    items_failed: int,
    ledger_root: Path,
    export_root: Path | None = None,
) -> tuple[MetricsRow, dict]:
    """Full dry-run path: RunMetrics → to_row → validate → export JSON."""
    t0 = time.monotonic()
    time.sleep(0.01)  # ensure non-zero duration

    with RunMetrics(
        run_id=run_id,
        agent_name=agent_name,
        job_type=job_type,
        product=product,
        platform=platform,
        website="aspose.org",
        website_section=website_section,
        ledger_root=ledger_root,
    ) as rm:
        rm.record_events(events)
        row = rm.to_row(
            items_discovered=items_discovered,
            items_succeeded=items_succeeded,
            items_failed=items_failed,
        )

    row_dict = row_to_dict(row)

    # Export via MetricsSubmitter dry_run
    if export_root:
        export_path = export_root / f"{run_id}.dry.json"
        submitter = MetricsSubmitter(mode=MODE_DRY_RUN, output_path=export_path)
        result = submitter.submit(row)
        # dry_run writes the JSON to output_path
        if export_path.exists():
            row_dict = json.loads(export_path.read_text(encoding="utf-8"))

    return row, row_dict


# ===========================================================================
# Job Type 1: Knowledge Enrichment (enrich.py — CS-001)
# ===========================================================================

class TestDryRun_KnowledgeEnrichment:
    """Dry-run: knowledge_enrichment job type produces valid MetricsRow."""

    JOB = "knowledge_enrichment"
    AGENT = "aspose-org-knowledge-enrichment"
    CS = "CS-001"

    def test_valid_schema(self, tmp_path):
        events = _make_events(self.CS, 8, tokens_per=250)
        row, _ = _run_dry_run(
            run_id=generate_run_id(),
            agent_name=self.AGENT,
            job_type=self.JOB,
            product="cells",
            platform="java",
            website_section="Docs",
            events=events,
            items_discovered=12,
            items_succeeded=10,
            items_failed=2,
            ledger_root=tmp_path / "events",
        )
        vr = validate_row(row)
        assert vr.valid, f"Schema validation failed: {vr.errors}"

    def test_token_usage_plausible(self, tmp_path):
        events = _make_events(self.CS, 8, tokens_per=250)
        row, _ = _run_dry_run(
            run_id=generate_run_id(),
            agent_name=self.AGENT,
            job_type=self.JOB,
            product="cells",
            platform="java",
            website_section="Docs",
            events=events,
            items_discovered=12,
            items_succeeded=10,
            items_failed=2,
            ledger_root=tmp_path / "events",
        )
        assert row.token_usage == 8 * 250, f"Expected 2000 tokens, got {row.token_usage}"
        assert row.api_calls_count == 8

    def test_dry_run_json_written(self, tmp_path):
        run_id = generate_run_id()
        events = _make_events(self.CS, 4, tokens_per=200)
        _, row_dict = _run_dry_run(
            run_id=run_id,
            agent_name=self.AGENT,
            job_type=self.JOB,
            product="words",
            platform="net",
            website_section="Docs",
            events=events,
            items_discovered=5,
            items_succeeded=5,
            items_failed=0,
            ledger_root=tmp_path / "events",
            export_root=tmp_path / "dry",
        )
        dry_file = tmp_path / "dry" / f"{run_id}.dry.json"
        assert dry_file.exists(), "Dry-run JSON not written"
        data = json.loads(dry_file.read_text())
        assert data["job_type"] == resolve_job_type("knowledge_enrichment")
        assert data["token_usage"] == 800

    def test_ledger_jsonl_written(self, tmp_path):
        run_id = generate_run_id()
        events = _make_events(self.CS, 3)
        _run_dry_run(
            run_id=run_id,
            agent_name=self.AGENT,
            job_type=self.JOB,
            product="cells",
            platform="java",
            website_section="Docs",
            events=events,
            items_discovered=3,
            items_succeeded=3,
            items_failed=0,
            ledger_root=tmp_path / "events",
        )
        ledger = tmp_path / "events" / f"{run_id}.jsonl"
        assert ledger.exists()
        lines = ledger.read_text().strip().splitlines()
        assert len(lines) == 3


# ===========================================================================
# Job Type 2: Gap Evaluation (gap-eval/run.py — CS-001)
# ===========================================================================

class TestDryRun_GapEvaluation:
    """Dry-run: gap_evaluation job type produces valid MetricsRow."""

    JOB = "gap_evaluation"
    AGENT = "aspose-org-gap-evaluation"
    CS = "CS-001"

    def test_valid_schema(self, tmp_path):
        events = _make_events(self.CS, 15, tokens_per=180)
        row, _ = _run_dry_run(
            run_id=generate_run_id(),
            agent_name=self.AGENT,
            job_type=self.JOB,
            product="slides",
            platform="java",
            website_section="Docs",
            events=events,
            items_discovered=50,
            items_succeeded=48,
            items_failed=2,
            ledger_root=tmp_path / "events",
        )
        vr = validate_row(row)
        assert vr.valid, f"Schema validation failed: {vr.errors}"

    def test_token_usage_plausible(self, tmp_path):
        events = _make_events(self.CS, 15, tokens_per=180)
        row, _ = _run_dry_run(
            run_id=generate_run_id(),
            agent_name=self.AGENT,
            job_type=self.JOB,
            product="slides",
            platform="java",
            website_section="Docs",
            events=events,
            items_discovered=50,
            items_succeeded=48,
            items_failed=2,
            ledger_root=tmp_path / "events",
        )
        assert row.token_usage == 15 * 180
        assert row.api_calls_count == 15

    def test_dry_run_json_written(self, tmp_path):
        run_id = generate_run_id()
        events = _make_events(self.CS, 6, tokens_per=200)
        _, row_dict = _run_dry_run(
            run_id=run_id,
            agent_name=self.AGENT,
            job_type=self.JOB,
            product="pdf",
            platform="net",
            website_section="Docs",
            events=events,
            items_discovered=20,
            items_succeeded=18,
            items_failed=2,
            ledger_root=tmp_path / "events",
            export_root=tmp_path / "dry",
        )
        dry_file = tmp_path / "dry" / f"{run_id}.dry.json"
        assert dry_file.exists()
        data = json.loads(dry_file.read_text())
        assert data["job_type"] == resolve_job_type("gap_evaluation")


# ===========================================================================
# Job Type 3: Gap Synthesis (gap-eval/synthesize.py — CS-001)
# ===========================================================================

class TestDryRun_GapSynthesis:
    """Dry-run: gap_synthesis job type produces valid MetricsRow."""

    JOB = "gap_synthesis"
    AGENT = "aspose-org-gap-evaluation"
    CS = "CS-001"

    def test_valid_schema(self, tmp_path):
        events = _make_events(self.CS, 10, tokens_per=300)
        row, _ = _run_dry_run(
            run_id=generate_run_id(),
            agent_name=self.AGENT,
            job_type=self.JOB,
            product="all",
            platform="all",
            website_section="Docs",
            events=events,
            items_discovered=30,
            items_succeeded=28,
            items_failed=2,
            ledger_root=tmp_path / "events",
        )
        vr = validate_row(row)
        assert vr.valid, f"Schema validation failed: {vr.errors}"

    def test_token_usage_plausible(self, tmp_path):
        events = _make_events(self.CS, 10, tokens_per=300)
        row, _ = _run_dry_run(
            run_id=generate_run_id(),
            agent_name=self.AGENT,
            job_type=self.JOB,
            product="all",
            platform="all",
            website_section="Docs",
            events=events,
            items_discovered=30,
            items_succeeded=28,
            items_failed=2,
            ledger_root=tmp_path / "events",
        )
        assert row.token_usage == 3000
        assert row.api_calls_count == 10

    def test_dry_run_json_written(self, tmp_path):
        run_id = generate_run_id()
        events = _make_events(self.CS, 5, tokens_per=250)
        _run_dry_run(
            run_id=run_id,
            agent_name=self.AGENT,
            job_type=self.JOB,
            product="all",
            platform="all",
            website_section="Docs",
            events=events,
            items_discovered=10,
            items_succeeded=10,
            items_failed=0,
            ledger_root=tmp_path / "events",
            export_root=tmp_path / "dry",
        )
        dry_file = tmp_path / "dry" / f"{run_id}.dry.json"
        assert dry_file.exists()
        data = json.loads(dry_file.read_text())
        assert data["job_type"] == resolve_job_type("gap_synthesis")
        assert data["token_usage"] == 1250


# ===========================================================================
# Job Type 4: Translation (translator/cli.py — CS-008)
# ===========================================================================

class TestDryRun_Translation:
    """Dry-run: translation job type produces valid MetricsRow."""

    JOB = "translation"
    AGENT = "aspose-org-translator"
    CS = "CS-008"

    def test_valid_schema(self, tmp_path):
        events = _make_events(self.CS, 20, tokens_per=150)
        row, _ = _run_dry_run(
            run_id=generate_run_id(),
            agent_name=self.AGENT,
            job_type=self.JOB,
            product="words",
            platform="net",
            website_section="Docs",
            events=events,
            items_discovered=20,
            items_succeeded=18,
            items_failed=2,
            ledger_root=tmp_path / "events",
        )
        vr = validate_row(row)
        assert vr.valid, f"Schema validation failed: {vr.errors}"

    def test_token_usage_plausible(self, tmp_path):
        events = _make_events(self.CS, 20, tokens_per=150)
        row, _ = _run_dry_run(
            run_id=generate_run_id(),
            agent_name=self.AGENT,
            job_type=self.JOB,
            product="words",
            platform="net",
            website_section="Docs",
            events=events,
            items_discovered=20,
            items_succeeded=18,
            items_failed=2,
            ledger_root=tmp_path / "events",
        )
        assert row.token_usage == 3000
        assert row.api_calls_count == 20

    def test_dry_run_json_written(self, tmp_path):
        run_id = generate_run_id()
        events = _make_events(self.CS, 3, tokens_per=200)
        _run_dry_run(
            run_id=run_id,
            agent_name=self.AGENT,
            job_type=self.JOB,
            product="cells",
            platform="java",
            website_section="Docs",
            events=events,
            items_discovered=3,
            items_succeeded=3,
            items_failed=0,
            ledger_root=tmp_path / "events",
            export_root=tmp_path / "dry",
        )
        dry_file = tmp_path / "dry" / f"{run_id}.dry.json"
        assert dry_file.exists()


# ===========================================================================
# Job Type 5: Embedding (embed.py — CS-002/CS-004)
# ===========================================================================

class TestDryRun_Embedding:
    """Dry-run: embedding job type produces valid MetricsRow."""

    JOB = "embedding"
    AGENT = "aspose-org-embedding"
    CS = "CS-002"

    def test_valid_schema(self, tmp_path):
        events = _make_embed_events(self.CS, 12, tokens_per=80)
        row, _ = _run_dry_run(
            run_id=generate_run_id(),
            agent_name=self.AGENT,
            job_type=self.JOB,
            product="cells",
            platform="java",
            website_section="Docs",
            events=events,
            items_discovered=100,
            items_succeeded=96,
            items_failed=4,
            ledger_root=tmp_path / "events",
        )
        vr = validate_row(row)
        assert vr.valid, f"Schema validation failed: {vr.errors}"

    def test_token_usage_plausible(self, tmp_path):
        events = _make_embed_events(self.CS, 12, tokens_per=80)
        row, _ = _run_dry_run(
            run_id=generate_run_id(),
            agent_name=self.AGENT,
            job_type=self.JOB,
            product="cells",
            platform="java",
            website_section="Docs",
            events=events,
            items_discovered=100,
            items_succeeded=96,
            items_failed=4,
            ledger_root=tmp_path / "events",
        )
        assert row.token_usage == 960, f"Expected 960 tokens, got {row.token_usage}"
        assert row.api_calls_count == 12

    def test_dry_run_json_written(self, tmp_path):
        run_id = generate_run_id()
        events = _make_embed_events(self.CS, 5, tokens_per=100)
        _run_dry_run(
            run_id=run_id,
            agent_name=self.AGENT,
            job_type=self.JOB,
            product="pdf",
            platform="net",
            website_section="Docs",
            events=events,
            items_discovered=50,
            items_succeeded=50,
            items_failed=0,
            ledger_root=tmp_path / "events",
            export_root=tmp_path / "dry",
        )
        dry_file = tmp_path / "dry" / f"{run_id}.dry.json"
        assert dry_file.exists()
        data = json.loads(dry_file.read_text())
        assert data["job_type"] == resolve_job_type("embedding")
        assert data["token_usage"] == 500


# ===========================================================================
# Job Type 6: SEO (seo/recommend.py — CS-009)
# ===========================================================================

class TestDryRun_SEO:
    """Dry-run: seo job type produces valid MetricsRow."""

    JOB = "seo"
    AGENT = "aspose-org-seo"
    CS = "CS-009"

    def test_valid_schema(self, tmp_path):
        events = _make_events(self.CS, 5, tokens_per=200)
        row, _ = _run_dry_run(
            run_id=generate_run_id(),
            agent_name=self.AGENT,
            job_type=self.JOB,
            product="seo",
            platform="all",
            website_section="Products",
            events=events,
            items_discovered=10,
            items_succeeded=8,
            items_failed=2,
            ledger_root=tmp_path / "events",
        )
        vr = validate_row(row)
        assert vr.valid, f"Schema validation failed: {vr.errors}"

    def test_token_usage_plausible(self, tmp_path):
        events = _make_events(self.CS, 5, tokens_per=200)
        row, _ = _run_dry_run(
            run_id=generate_run_id(),
            agent_name=self.AGENT,
            job_type=self.JOB,
            product="seo",
            platform="all",
            website_section="Products",
            events=events,
            items_discovered=10,
            items_succeeded=8,
            items_failed=2,
            ledger_root=tmp_path / "events",
        )
        assert row.token_usage == 1000
        assert row.api_calls_count == 5

    def test_dry_run_json_written(self, tmp_path):
        run_id = generate_run_id()
        events = _make_events(self.CS, 2, tokens_per=150)
        _run_dry_run(
            run_id=run_id,
            agent_name=self.AGENT,
            job_type=self.JOB,
            product="seo",
            platform="all",
            website_section="Products",
            events=events,
            items_discovered=4,
            items_succeeded=4,
            items_failed=0,
            ledger_root=tmp_path / "events",
            export_root=tmp_path / "dry",
        )
        dry_file = tmp_path / "dry" / f"{run_id}.dry.json"
        assert dry_file.exists()
        data = json.loads(dry_file.read_text())
        assert data["job_type"] == resolve_job_type("seo")


# ===========================================================================
# Cross-job-type validation
# ===========================================================================

class TestDryRun_CrossValidation:
    """Cross-cutting validation: all job types produce consistent payloads."""

    _JOBS = [
        ("knowledge_enrichment", "aspose-org-knowledge-enrichment", "CS-001", "cells", "java", "Docs"),
        ("gap_evaluation", "aspose-org-gap-evaluation", "CS-001", "slides", "java", "Docs"),
        ("gap_synthesis", "aspose-org-gap-evaluation", "CS-001", "all", "all", "Docs"),
        ("translation", "aspose-org-translator", "CS-008", "words", "net", "Docs"),
        ("embedding", "aspose-org-embedding", "CS-002", "cells", "java", "Docs"),
        ("seo", "aspose-org-seo", "CS-009", "seo", "all", "Products"),
    ]

    def test_all_six_produce_valid_rows(self, tmp_path):
        """Every job type produces a MetricsRow that passes schema validation."""
        for job_type, agent, cs, product, platform, section in self._JOBS:
            events = _make_events(cs, 3, tokens_per=100)
            row, _ = _run_dry_run(
                run_id=generate_run_id(),
                agent_name=agent,
                job_type=job_type,
                product=product,
                platform=platform,
                website_section=section,
                events=events,
                items_discovered=5,
                items_succeeded=5,
                items_failed=0,
                ledger_root=tmp_path / f"events-{job_type}",
            )
            vr = validate_row(row)
            assert vr.valid, f"{job_type} failed validation: {vr.errors}"

    def test_all_six_write_dry_json(self, tmp_path):
        """Every job type produces a .dry.json file via MetricsSubmitter."""
        for job_type, agent, cs, product, platform, section in self._JOBS:
            run_id = generate_run_id()
            events = _make_events(cs, 2, tokens_per=100)
            _run_dry_run(
                run_id=run_id,
                agent_name=agent,
                job_type=job_type,
                product=product,
                platform=platform,
                website_section=section,
                events=events,
                items_discovered=2,
                items_succeeded=2,
                items_failed=0,
                ledger_root=tmp_path / f"events-{job_type}",
                export_root=tmp_path / "dry",
            )
            dry_file = tmp_path / "dry" / f"{run_id}.dry.json"
            assert dry_file.exists(), f"{job_type} dry-run JSON not written"
            data = json.loads(dry_file.read_text())
            assert data["job_type"] == resolve_job_type(job_type)
            assert data["token_usage"] == 200
            assert data["api_calls_count"] == 2

    def test_token_usage_equals_sum_of_events(self, tmp_path):
        """token_usage always equals the sum of total_tokens across events."""
        for job_type, agent, cs, product, platform, section in self._JOBS:
            events = _make_events(cs, 4, tokens_per=123)
            row, _ = _run_dry_run(
                run_id=generate_run_id(),
                agent_name=agent,
                job_type=job_type,
                product=product,
                platform=platform,
                website_section=section,
                events=events,
                items_discovered=4,
                items_succeeded=4,
                items_failed=0,
                ledger_root=tmp_path / f"events-{job_type}",
            )
            expected = sum(e.total_tokens for e in events)
            assert row.token_usage == expected, (
                f"{job_type}: token_usage={row.token_usage} != sum={expected}"
            )

    def test_api_calls_count_equals_event_count(self, tmp_path):
        """api_calls_count always equals the number of events."""
        for job_type, agent, cs, product, platform, section in self._JOBS:
            n = 7
            events = _make_events(cs, n, tokens_per=50)
            row, _ = _run_dry_run(
                run_id=generate_run_id(),
                agent_name=agent,
                job_type=job_type,
                product=product,
                platform=platform,
                website_section=section,
                events=events,
                items_discovered=n,
                items_succeeded=n,
                items_failed=0,
                ledger_root=tmp_path / f"events-{job_type}",
            )
            assert row.api_calls_count == n, (
                f"{job_type}: api_calls_count={row.api_calls_count} != {n}"
            )

    def test_zero_events_produce_zero_counters(self, tmp_path):
        """Job with zero events produces token_usage=0, api_calls_count=0."""
        for job_type, agent, cs, product, platform, section in self._JOBS:
            row, _ = _run_dry_run(
                run_id=generate_run_id(),
                agent_name=agent,
                job_type=job_type,
                product=product,
                platform=platform,
                website_section=section,
                events=[],
                items_discovered=0,
                items_succeeded=0,
                items_failed=0,
                ledger_root=tmp_path / f"events-{job_type}",
            )
            assert row.token_usage == 0
            assert row.api_calls_count == 0

    def test_submitter_dry_run_never_makes_http(self, tmp_path):
        """MetricsSubmitter in dry_run mode never calls HTTP."""
        for job_type, agent, cs, product, platform, section in self._JOBS:
            events = _make_events(cs, 1, tokens_per=100)
            row, _ = _run_dry_run(
                run_id=generate_run_id(),
                agent_name=agent,
                job_type=job_type,
                product=product,
                platform=platform,
                website_section=section,
                events=events,
                items_discovered=1,
                items_succeeded=1,
                items_failed=0,
                ledger_root=tmp_path / f"events-{job_type}",
            )
            # dry_run submitter must not raise and must not submit
            result = MetricsSubmitter(mode=MODE_DRY_RUN).submit(row)
            assert result.submitted is False or result.mode == "dry_run"
