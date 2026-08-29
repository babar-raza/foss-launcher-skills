---
name: workflow-harden
id: S-121
description: >
  Manually review every CI workflow file (GitHub Actions and/or GitLab CI)
  for correctness, fragility, and unnecessary weight, using a fixed
  8-dimension probe and severity taxonomy. Generalized from aspose.org's
  workflow-harden skill (S-115) -- ported 2026-08-29.
args: "[--workflow <file>] [--investigate-only] [--max-findings N]"
---

# S-121: Workflow Harden -- CI Workflow Audit & Hardening

**Arguments**: $ARGUMENTS (all optional)

## Purpose
Review every CI workflow file this repo runs -- `.github/workflows/*.yml`
and/or `.gitlab-ci.yml` (this repo has both, per ADR-003's dual-CI design;
check which are actually present rather than assuming) -- classify defects
and fragility using a fixed taxonomy, and fix what's safe to fix in the
same pass: missing safeguards (timeouts), correctness gaps (a
soft-failing step whose output a later blocking step trusts
unconditionally), permission/credential scope issues, and opportunities to
make CI lighter without weakening any gate.

**Not a content skill.** Never writes to content or a connected content
repo. Modifies only `.github/workflows/*.yml`, `.gitlab-ci.yml`, composite
actions, and CI support scripts.

## Adaptation note (generalized from source)
Source's version assumes a single CI system with no dual-CI equivalent to
this repo's own GitHub Actions + GitLab CI setup, and is built on
source-repo-specific checkpoint/taskcard infrastructure (a skill-context
begin/end gate, an override-token manager, a schema-versioned taskcard
JSON format) this repo does not have. This port keeps the genuinely portable
part -- the 8-dimension probe and severity taxonomy below, which apply to
any CI system -- and drops the elaborate multi-phase checkpoint/resume
machinery in favor of a single pass with a plain findings report. If this
repo's own governance later grows an equivalent taskcard system, revisit
whether to adopt the fuller structure.

## Pre-conditions
1. Git working tree clean for the CI files this skill will touch.
2. `.venv/bin/python` (this repo's venv interpreter) resolves.
3. `gh auth status` succeeds if GitHub Actions workflows are in scope and
   remote verification (`gh workflow run` / `gh run watch`) is wanted.

## Hard limits
- **Max findings**: default 30; exceeding this halts and escalates rather
  than silently truncating.
- **Never weaken a gate**: no removing matrices, no converting a blocking
  check to soft-fail to manufacture green, no widening `permissions:`
  beyond what the finding's own investigation justifies.
- **No secret rotation**: credential/PAT scope concerns are recorded as
  findings with a recommendation only.
- **Lightening must not reduce coverage**: caching, step consolidation, or
  trigger narrowing must not skip work a step was created to do.

## Steps

### 1. Inventory
List every workflow file in scope (`.github/workflows/*.yml`,
`.gitlab-ci.yml`, and any composite/included actions or templates they
reference). Confirm which CI systems are actually active -- do not assume;
check for both directories/files.

### 2. Apply the 8-dimension probe to every workflow

| Probe | Question |
|-------|----------|
| P-01: Trigger/rules correctness | Are branch/path filters and event-type behavior (PR vs push vs schedule vs manual dispatch) correct and non-redundant? |
| P-02: Dependency/execution graph | Are job ordering and concurrency groups correct? Any race conditions? |
| P-03: Runner/environment | Is the runner target what's documented/expected -- no undocumented self-hosted or ambiguous-label assumptions? |
| P-04: Permissions & secrets | Least-privilege permission scopes; secrets referenced only where needed; nothing hardcoded |
| P-05: Action/dependency integrity | Third-party actions/images pinned to a version tag or SHA (not a floating branch); nothing deprecated |
| P-06: Build/test/lint correctness | Do commands actually validate what they claim; any swallowed exit codes; does a soft-failing step feed a later blocking step's input unconditionally? |
| P-07: Cache/artifact correctness | Cache keys correct and non-contaminating; artifacts produced/consumed correctly |
| P-08: CI weight | Redundant steps, missing dependency caching, unnecessary step count for what the job actually verifies |

Record each finding with: file, probe, title, detail, severity, line
reference.

### 3. Classify each finding

Taxonomy: `CONFIRMED_DEFECT | CONFIRMED_FRAGILITY | CONFIGURATION_DRIFT | CREDENTIAL_OR_PERMISSION_DEFECT | SECURITY_RISK | OBSERVABILITY_GAP | MAINTAINABILITY_GAP | HEALTHY_WITH_EVIDENCE`

Severity:

| Tier | Criteria |
|------|----------|
| CRITICAL | Secret-leak risk, silent false-green on a blocking check, supply-chain compromise vector |
| HIGH | Missing timeout risking an indefinite hang; a soft-failing step whose output a blocking step trusts unconditionally |
| MEDIUM | Missing cache causing avoidable CI weight; broader credential scope than demonstrably needed |
| LOW | Style/consistency, SHA-pinning opportunity, minor redundant steps |

**Hard stop**: finding count > `--max-findings` -> stop and report rather
than continuing past the cap.

If `--investigate-only`, stop here and report findings without applying fixes.

### 4. Fix what's safe to fix
Typical safe fixes: add missing timeouts; add dependency caching; resolve
a soft-failing step whose output a later blocking step consumes
unconditionally (either make the step itself blocking, or make the
consumer explicitly validate/fail on a missing artifact). Anything
requiring a credential/permission change beyond what's already granted is
recorded as a finding with a recommendation, not applied directly.

### 5. Verify
- Local: YAML-parse every changed file; run `actionlint` if available,
  otherwise note the gap explicitly rather than skipping verification silently.
- Remote (GitHub Actions): for `workflow_dispatch`-enabled workflows,
  trigger a real run and confirm green; for push-triggered workflows,
  monitor the next natural run.
- Remote (GitLab CI): trigger a pipeline run if the platform supports it
  from the CLI available; otherwise monitor the next natural run.

### 6. Write the findings report
`reports/workflow-harden/{date}/findings.md` -- every workflow reviewed,
its findings (or an explicit HEALTHY verdict), fixes applied, and anything
deferred with a reason.

## Output
`reports/workflow-harden/{date}/findings.md`

## Post-conditions
- Every workflow file in scope has either a recorded finding or an explicit
  HEALTHY_WITH_EVIDENCE verdict -- nothing silently unreviewed.
- No mandatory/blocking check was removed or weakened.
- Every HIGH/CRITICAL finding is either fixed or explicitly deferred with a reason.

## Related Skills
None yet in this repo -- see the "Adaptation note" above for what this
skill deliberately does not carry over from its source.
