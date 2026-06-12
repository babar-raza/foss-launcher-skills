# Changelog

All notable changes to this project will be documented in this file.

The format is based on [Keep a Changelog](https://keepachangelog.com/en/1.0.0/),
and this project adheres to [Semantic Versioning](https://semver.org/spec/v2.0.0.html).

## [Unreleased]

### Fixed
- Coverage threshold corrected: the v0.2.0 entry incorrectly stated
  `fail_under` was raised to 70%. The actual enforced CI threshold is 12%
  (matching `pyproject.toml`). The 70% target is aspirational and tracked in
  the backlog. `--cov-fail-under=12` is the current honest gate.
- CI trigger paths expanded from `scripts/pipeline/**` to `scripts/**` so
  changes to core scripts (`discover.py`, `pre_write.py`, `path_guard.py`,
  `local_gate.py`, etc.) now correctly trigger the pipeline-tests workflow.
- E2E test file (`tests/test_e2e_pipeline.py`) no longer silently excluded
  via `--ignore`; now properly skipped via `pytestmark = pytest.mark.integration`
  using `-m "not scout and not integration"`.

### Added
- `Dockerfile` and `docker-compose.yml` for containerized tool execution (P4 signal)
- `scripts/pipeline_orchestrator.py` — Python state machine for multi-skill
  pipeline runs with JSON persistence, HITL gate, and retry budget enforcement
- `tests/test_pipeline_orchestrator.py` — 20+ tests covering state transitions,
  persistence, gate approval/rejection, retry budget, and invalid transitions
- `docs/adr/` directory with 5 architectural decision records:
  - ADR-001: Multi-skill chain architecture
  - ADR-002: Evidence-first content generation
  - ADR-003: Dual CI/CD (GitHub Actions + GitLab CI)
  - ADR-004: Python + tree-sitter for knowledge extraction
  - ADR-005: Content repository separation
- `scripts/generate_release_receipt.py` — generates signed release attestation
  to `docs/release-receipts/<version>.json`

---

## [0.2.0] - 2026-06-11

### Added
- `adaptive_retry.py` — retry wrapper with exponential backoff and static fallback map (S-21→S-26, S-26→S-78, S-20→S-21, S-25→S-32)
- `run_outcome_log.py` — append-only JSONL log for skill execution outcomes with correlation ID support, run-level metrics summary, and checkpoint/resume capability
- `test_adaptive_retry.py` — comprehensive tests for retry behavior including exhaustion, fallback map, and timing
- `test_run_outcome_log.py` — tests for outcome logging, correlation IDs, summarize_run, and checkpoint/resume
- `test_property_based.py` — hypothesis property-based tests for grounding score bounds, path guard invariants, and YAML roundtrip
- `test_security_basics.py` — security integration tests covering path traversal, YAML safe_load, hardcoded secret detection, and eval/exec blocking
- `CODEOWNERS` — PR review routing for all repository paths
- `CONTRIBUTING.md` — development setup, code style, PR process, and release workflow
- `SECURITY.md` — vulnerability reporting policy and automated security controls
- `docs/governance/incident-response.md` — severity-tiered incident response with escalation paths and postmortem template
- `docs/governance/reviewer-readiness-checklist.md` — A/P/R dimension evidence map for Recruitize readiness review
- `local_gate.py` entry point registered as `foss-gate` in pyproject.toml
- `fetch_aspose_com_targets.py` — sitemap fetcher for Aspose product backlink targets with HTTP verification and JSON/YAML export
- S-110 pipeline-harden skill — parameterized pipeline hardening sprint orchestrator

### Changed
- `pyproject.toml`: coverage `fail_under` kept at current achieved threshold (see Unreleased correction above)
- `.github/workflows/pipeline-tests.yml`: security-scan job promoted to blocking
- `parse_audit_fails.py`: improved FAIL-level finding extraction with file/line context
- `fetch_aspose_com_targets.py`: added P0/P1/P2 priority tiers, HTTP HEAD→GET fallback, synthesized URL support
- `m2m.py`: updated M2M100 translation backend with Hugging Face cache inspection

### Fixed
- Python 3.12+ f-string backslash syntax compatibility
- CI git installation for commit-provenance check
- Internal skills excluded from `.claude/commands/` sync

---

## [0.1.0] - 2026-04-01

### Added
- Initial standalone port from aspose.org infrastructure (203 core files)
- 93 skills covering pipeline, maintenance, generation, validation, evidence, gap-eval, quality, audit, orchestration, session/workflow, translation (S-01 through S-110)
- Knowledge pipeline: scout (tree-sitter extraction) → merge → index → embed
- Content pipeline: plan → draft → enhance → update → heal
- Validation pipeline: ground-check → verify → evidence-verify → truth-audit
- Evidence pipeline: materialize → decide → evidence-materialize
- `path_guard.py` — deterministic write-path governance with allowlist/denylist
- `pre_write.py` — pre-write gate with stale knowledge detection
- `local_gate.py` — pre-push local quality gate (registry, sync, schema, tests)
- `adaptive_retry.py` — retry with exponential backoff and fallback suggestions
- `launcher_adapter.py` — upstream launcher boundary layer
- AGENTS.md — 59KB comprehensive agent governance specification
- CLAUDE.md — agent ground rules and forbidden write paths
- pyproject.toml — package configuration with 7 entry points
- pytest.ini — test configuration with scout/integration markers
- config.yaml — site path templates and governance configuration
- 66 test modules covering all major features (772+ tests)
- GitHub Actions workflows: pipeline-tests, eval-consistency, skill-governance, skill-registry-audit
- GitLab CI: .gitlab-ci.yml with registry/sync/schema validation
- Security scanning: bandit SAST, pip-audit dependency scanning
- Golden corpus: 3 samples per site type for conformance checking
- Operator guide, quickstart guide, codex guidelines

[Unreleased]: https://github.com/aspose-org/foss-launcher-skills/compare/v0.2.0...HEAD
[0.2.0]: https://github.com/aspose-org/foss-launcher-skills/compare/v0.1.0...v0.2.0
[0.1.0]: https://github.com/aspose-org/foss-launcher-skills/releases/tag/v0.1.0
