# ADR-003: Dual CI/CD (GitHub Actions + GitLab CI)

**Date:** 2026-04-27
**Status:** Accepted
**Deciders:** @prora

## Context

The skills repo is hosted on GitHub but needs to operate in environments where GitLab is the primary CI/CD platform. The target Aspose FOSS content repo uses GitLab pipelines, and operators working in that context expect CI results to be available in GitLab.

## Decision

We maintain **two parallel CI/CD configurations**:

1. **GitHub Actions** (`.github/workflows/`): Primary CI pipeline, runs on every push to `main` and on PRs. Contains: `pipeline-tests`, `skill-registry-audit`, `eval-consistency`, `skill-governance`, `release`.

2. **GitLab CI** (`.gitlab-ci.yml`): Mirror CI pipeline with equivalent stages. Provides validation for operators using the GitLab remote. Contains: registry-integrity, commands-sync, agents-sync, readme-currency, internal-skills, schema-validation, security-scan, governance-tests, commit-provenance.

Both pipelines enforce the same quality gates: skill registry integrity, test coverage, security scanning (bandit + pip-audit), and schema validation.

## Sync Strategy

GitLab CI is kept in sync manually when GitHub Actions workflows change. Key divergences are acceptable (GitLab-specific syntax for coverage reporting, artifact paths) but the test commands and gates must be equivalent.

## Alternatives Considered

- **GitHub Actions only**: Rejected — operators on GitLab remote have no local CI feedback.
- **GitLab CI only**: Rejected — GitHub is the primary repository and the GitHub Actions ecosystem provides better marketplace integrations.
- **CI/CD abstraction layer (e.g., a shared Makefile)**: Considered for future — would reduce duplication. Not implemented yet due to complexity.

## Consequences

- CI changes must be applied to both pipelines (maintenance overhead)
- Quality gates are consistently enforced in both environments
- Drift between GitHub and GitLab CI is a risk; the skill-governance workflow checks for this

## Implementation

- GitHub Actions: [`.github/workflows/`](../../.github/workflows/)
- GitLab CI: [`.gitlab-ci.yml`](../../.gitlab-ci.yml)
- Local gate (equivalent to both): [`scripts/local_gate.py`](../../scripts/local_gate.py)
