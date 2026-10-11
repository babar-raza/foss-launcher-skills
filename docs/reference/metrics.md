# Metrics Reference

Status: Current
Audience: Contributor, Operator
Canonical reference: this page
Last code-backed audit: 2026-05-30

Metrics capture covers professionalize API calls and work-slice row aggregation.

## Data Structures

| Structure | Code | Purpose |
|---|---|---|
| `MetricsEvent` | `scripts/pipeline/commands/ops/metrics_schema.py` | One captured professionalize API call. |
| `MetricsRow` | `scripts/pipeline/commands/ops/metrics_schema.py` | 17-field work-slice row. |
| `MetricsEventLedger` | `scripts/pipeline/commands/ops/metrics_event_ledger.py` | JSONL event ledger. |
| `RunMetrics` | `scripts/pipeline/commands/ops/run_metrics.py` | Context manager that records events and builds rows. |

## Event Ledger

Default event ledger path:

```text
reports/metrics/events/{run_id}.jsonl
```

The ledger validates events before writing and rejects path traversal in run IDs.

## LLM Routing

LLM provider config lives in `scripts/pipeline/config/llm_registry.yaml`; see [configuration](config.md#llm-routing).

## Operations

See [Telemetry and metrics](../operations/telemetry-and-metrics.md).
