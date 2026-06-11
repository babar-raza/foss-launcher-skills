# Changelog

All notable changes to this project will be documented in this file.

The format is based on [Keep a Changelog](https://keepachangelog.com/en/1.0.0/),
and this project adheres to [Semantic Versioning](https://semver.org/spec/v2.0.0.html).

## [Unreleased]

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
- `pyproject.toml`: coverage `fail_under` raised from 11% to 70% to align with CI gate
- `.github/workflows/pipeline-tests.yml`: added explicit `--cov-fail-under=70` to pytest command; security-scan job promoted to blocking
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

[Unreleased]: https://github.com/aspose-org/foss-launcher-skills/compare/v0.1.0...HEAD
[0.1.0]: https://github.com/aspose-org/foss-launcher-skills/releases/tag/v0.1.0
