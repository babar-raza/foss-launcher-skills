# Reviewer-Readiness Checklist

Maps Recruitize A/P/R dimensions to project evidence. Every row links to actual files.

## A-Axis (Agentic) Evidence

| Feature | Evidence File | Test | CI Job |
|---------|--------------|------|--------|
| Decision engine (branching) | scripts/decide.py | tests/test_decide.py | pipeline-tests |
| Verification engine | scripts/verify.py | tests/test_verify.py | pipeline-tests |
| Skill chain resolver (DAR) | scripts/pipeline/commands/ops/skill_chain.py | tests/test_skill_chain.py | governance-tests |
| Path guard (approval gate) | scripts/pipeline/commands/governance/path_guard.py | tests/test_path_guard.py | governance-tests |
| Readiness gate (multi-gate) | scripts/pipeline/commands/launch/readiness_gate.py | tests/test_readiness_gate.py | governance-tests |
| Causal backtracking | scripts/pipeline/commands/healing/backtrack_controller.py | tests/test_backtrack_controller.py | governance-tests |
| Adaptive retry (A7) | scripts/pipeline/commands/ops/adaptive_retry.py | tests/test_adaptive_retry.py | pipeline-tests |
| Run outcome feedback (A7) | scripts/pipeline/commands/ops/run_outcome_log.py | tests/test_run_outcome_log.py | pipeline-tests |
| Skill run manager | scripts/pipeline/skill_run_manager.py | tests/test_skill_run_manager.py | governance-tests |
| Checkpoint/resume (S-38) | skills/launch-product.md | -- | -- |

## P-Axis (Practices) Evidence

| Practice | Evidence File | CI Job |
|----------|--------------|--------|
| Test framework (pytest) | pyproject.toml [tool.pytest] | pipeline-tests, governance-tests |
| Coverage gate (70%) | pyproject.toml [tool.coverage] fail_under=70 | pipeline-tests |
| Multi-stage CI (GitHub) | .github/workflows/skill-governance.yml (8 jobs) | skill-governance |
| Multi-stage CI (GitLab) | .gitlab-ci.yml (validate + test stages) | gitlab-ci |
| SAST scanning (bandit) | scripts/ci/checks/check_sast_bandit.py | security-scan |
| Dependency scanning | scripts/ci/checks/check_dependency_audit.py | security-scan |
| Secrets detection | scripts/ci/checks/check_metrics_no_secrets.py | -- |
| Structured logging | scripts/ops_log.py (JSONL) | -- |
| Metrics subsystem | scripts/pipeline/commands/ops/metrics_*.py | -- |
| Property-based tests | tests/test_property_based.py (hypothesis) | pipeline-tests |
| Security tests | tests/test_security_basics.py | pipeline-tests |
| Local quality gate | scripts/local_gate.py | -- |
| 63 CI check scripts | scripts/ci/checks/*.py | various |
| Schema validation | scripts/schema_validate.py | schema-validation |

## R-Axis (Readiness) Evidence

| Artifact | File | Verification |
|----------|------|-------------|
| README | README.md (21KB) | readme-currency CI job |
| Quickstart guide | QUICKSTART.md | manual |
| Operator guide | OPERATORS_GUIDE.md | manual |
| Runbook | docs/RUNBOOK.md | manual |
| Changelog | reports/CHANGELOG.md | manual |
| Security policy | SECURITY.md | manual |
| Contributing guide | CONTRIBUTING.md | manual |
| Code ownership | CODEOWNERS | GitHub auto-review |
| Governance (AGENTS.md) | AGENTS.md (59KB) | check_agents_md_size.py |
| Skill registry | skills/registry.yaml (92 skills) | registry-integrity CI job |
| Architecture decisions | docs/governance/*.md (11 files) | manual |
| Incident response | docs/governance/incident-response.md | manual |
| Audit trail | reports/ops.log (JSONL) | check_report_freshness.py |
| Release tag | v0.1.0 (git tag) | git tag -l |
| Config schema | configs/schemas/config.schema.json | schema-validation CI job |
| Approval gates | docs/governance/launch-gates.md | readiness_gate.py |
| Commit provenance | commit-provenance CI job | .gitlab-ci.yml |
