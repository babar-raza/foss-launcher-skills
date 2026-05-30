# Testing And CI

Status: Current
Audience: Contributor, Agent
Canonical reference: this page
Last code-backed audit: 2026-05-30

## Pytest Configuration

`pytest.ini` defines:

| Setting | Value |
|---|---|
| `testpaths` | `tests`, `scripts/pipeline/tests`, `scripts/translator/tests` |
| `pythonpath` | `scripts/pipeline`, `scripts/translator` |

## Test Selection

Run focused tests first, then broaden when the change touches shared contracts.

Common surfaces:

| Surface | Example tests |
|---|---|
| Clone cache | `scripts/pipeline/tests/test_clone_cache.py` |
| Audit | `scripts/pipeline/tests/test_audit.py` |
| Evidence | `scripts/pipeline/tests/test_attach_evidence_behavior.py` |
| Content eval | `scripts/pipeline/tests/content_eval/` |
| Metrics | `scripts/pipeline/tests/test_metrics_event_ledger.py`, `test_run_metrics.py` |
| Site planning | `scripts/pipeline/tests/test_site_planner.py` |
| Hooks | `scripts/ci/tests/` |

## CI Coverage

The content audit workflow checks content filename conventions, audit regressions, grade integrity, strict content evaluation, frontmatter, skill sync, clone-cache references, pipeline registration, and Python placement.

See [governance gates](../reference/governance-gates.md).
