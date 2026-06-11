# Phase 0 — Target and Reviewer Isolation Proof

**Sprint timestamp:** 2026-06-10T16:00:00Z
**Sprint run ID:** 2026-06-10-recruitize-current-project

## Path Resolution

| Variable | Value |
|----------|-------|
| RUNNER_WORKSPACE | c:\Users\prora\OneDrive\Documents\GitHub\foss-launcher-skills-gitlab |
| TARGET_PROJECT_PATH | c:\Users\prora\OneDrive\Documents\GitHub\foss-launcher-skills-gitlab |
| TARGET_PROJECT_RESOLVED_PATH | c:\Users\prora\OneDrive\Documents\GitHub\foss-launcher-skills-gitlab |
| REVIEWER_PROJECT_PATH | C:\Users\prora\OneDrive\Documents\GitHub\recruitize-ai-review-agent |
| REVIEWER_PROJECT_RESOLVED_PATH | C:\Users\prora\OneDrive\Documents\GitHub\recruitize-ai-review-agent |
| IS_TARGET_SAME_AS_REVIEWER | **false** |

These are distinct repositories on different paths. The target is not the reviewer.

## Target Project Confirmed

- Git root: `c:\Users\prora\OneDrive\Documents\GitHub\foss-launcher-skills-gitlab`
- Branch: `main`
- Language: Python 3.11+
- Build system: setuptools (pyproject.toml)
- Test framework: pytest + hypothesis
- CI: GitHub Actions (.github/workflows/), GitLab CI (.gitlab-ci.yml)
- Entry points: foss-audit, foss-check, foss-gate, foss-materialize, foss-verify, foss-decide, foss-validate
- Skills: 93 total (86 user-callable, 7 internal)

## Reviewer Project Confirmed Read-Only

- Path: `C:\Users\prora\OneDrive\Documents\GitHub\recruitize-ai-review-agent`
- Language: Node.js/JavaScript (ESM)
- Status: INSPECTED IN READ-ONLY MODE — no files modified
- Rating dimensions confirmed: Agentic (40%), Engineering (30%), Readiness (30%)

## Mutation Safety Pledge

All file mutations during this sprint are confined to:

```
c:\Users\prora\OneDrive\Documents\GitHub\foss-launcher-skills-gitlab\
```

Override tokens created for root-level and .github/ paths:
- Token ID: 20260610-160011-pyproject-toml
- Covers: pyproject.toml, CHANGELOG.md, CONTRIBUTING.md, github/workflows/pipeline-tests.yml

## Initial Git Status

Modified (tracked, pre-sprint):
- .github/workflows/pipeline-tests.yml
- scripts/ci/checks/parse_audit_fails.py
- scripts/pipeline/commands/ops/fetch_aspose_com_targets.py
- scripts/translator/backends/m2m.py

Untracked (new, on-disk but not yet committed):
- CODEOWNERS, CONTRIBUTING.md, SECURITY.md
- coverage.json
- docs/governance/incident-response.md
- docs/governance/reviewer-readiness-checklist.md
- reports/claim-coverage-2026-06-10.md, reports/score-readiness-2026-06-10.md
- scripts/pipeline/commands/ops/adaptive_retry.py
- scripts/pipeline/commands/ops/run_outcome_log.py
- tests/test_adaptive_retry.py, tests/test_property_based.py
- tests/test_run_outcome_log.py, tests/test_security_basics.py

## Sprint Scope Boundaries

Writes attempted only under TARGET_PROJECT_RESOLVED_PATH.
Reviewer project: READ-ONLY throughout this sprint.
