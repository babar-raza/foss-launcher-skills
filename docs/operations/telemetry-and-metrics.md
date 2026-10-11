# Telemetry And Metrics

Status: Current
Audience: Operator, Contributor
Canonical reference: `docs/reference/metrics.md`
Last code-backed audit: 2026-05-30

Metrics are captured for professionalize API calls and aggregated into run rows.

## Operational Contract

- Event ledgers are local JSONL files under `reports/metrics/events/`.
- Metrics schema and validation are owned by [Metrics reference](../reference/metrics.md).
- LLM provider routing is owned by [Configuration reference](../reference/config.md#llm-routing).

## Verification

- Event files contain one JSON object per line.
- No prompts, completions, or secrets are stored in metrics event fields.
- Row aggregation uses the schema fields documented in [Metrics reference](../reference/metrics.md).
