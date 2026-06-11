# Service Level Agreements (SLA)

**Owner:** See CODEOWNERS
**Last updated:** 2026-06-11
**Review cycle:** Quarterly

---

## Skill Execution SLA

| Metric | Target | Enforcement |
|--------|--------|-------------|
| Per-skill execution time | <= 60 seconds | adaptive_retry.py timeout; CI job timeout |
| Retry budget per skill | <= 3 attempts | max_retries=3 default in adaptive_retry.py |
| Pipeline end-to-end time | <= 10 minutes | CI timeout-minutes: 10 |

Skills that exceed 60 seconds are considered failures and trigger the retry/fallback mechanism defined in adaptive_retry.py.

---

## Content Freshness SLA

| Metric | Target | Enforcement |
|--------|--------|-------------|
| model.yaml freshness | Refreshed within 30 days of upstream release | stale_detect.py; pre_write.py stale check |
| Knowledge index staleness | Regenerated after any model.yaml update | knowledge-update skill (S-14) |
| Content pages after knowledge update | Updated within 1 sprint cycle | page-update skill (S-20) |

If model.yaml has stale_since set, pre_write.py blocks content edits and requires running the maintenance workflow (S-12 to S-14) before proceeding.

---

## CI Pipeline SLA

| Metric | Target | Notes |
|--------|--------|-------|
| PR gate time (all checks) | <= 10 minutes | Local gate should pass before pushing |
| Security scan blocking | On every push to main | bandit scan in pipeline-tests.yml |
| Coverage enforcement | Minimum 12% (current) | Incremental improvement planned |
| Skill registry integrity | 100% on every commit | Pre-commit hook validates all 93 skills |

---

## Incident Response SLA

Derived from docs/governance/incident-response.md:

| Severity | First Response | Mitigation Target | Postmortem |
|----------|---------------|-------------------|-----------|
| P1 (content corruption) | 2 hours | 4 hours | Required within 48 hours |
| P2 (pipeline failure) | 4 hours | 8 hours | Required within 1 week |
| P3 (degraded output) | 1 business day | 3 business days | Optional |

---

## Release SLA

| Metric | Target |
|--------|--------|
| CHANGELOG entry | Required before tagging any version |
| Versioned tag format | v{MAJOR}.{MINOR}.{PATCH} (semver) |
| Release notes | Auto-extracted from CHANGELOG by release.yml |

---

## Exclusions

These SLAs apply to the skills pipeline and content generation system only.
They do not apply to:
- The upstream Aspose FOSS repositories (tracked as external dependencies)
- Human-authored content pages registered via S-71
- The Recruitize AI review agent (external system)
