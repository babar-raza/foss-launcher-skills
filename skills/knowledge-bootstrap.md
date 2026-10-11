# S-54: Knowledge Bootstrap - Shared Pre-condition Gate

**Arguments**: $ARGUMENTS
Expected format: `{family} {platform}` - e.g. `3d python`

## Purpose

Single reusable command that detects and resolves knowledge state before any content or validation
command proceeds. Outputs a structured status line that calling commands act on.

## Output Protocol

This command always prints exactly one of the following as its final output line:

| Status | Meaning |
|---|---|
| `KNOWLEDGE: READY` | Knowledge exists, is current, and has no blocking issues |
| `KNOWLEDGE: BOOTSTRAPPED` | Was absent (first-time setup); ran /repo-scout + /knowledge-enrich + /truth-merge; now ready |
| `KNOWLEDGE: REFRESHED` | Was stale; ran refresh_knowledge.py; now current |
| `KNOWLEDGE: WARN:conflicts` | Has unresolved merge conflicts (listed above); proceeding with caution |
| `KNOWLEDGE: STOP:partial` | Directory exists but merged/ is missing - human action required; halted |

## Steps

> **Skill context gate** — run before step 1:
> ```bash
> PYTHONPATH=scripts/pipeline .venv/Scripts/python scripts/pipeline/commands/governance/skill_context.py begin --skill S-54 --scope "*"
> ```


1. **Parse arguments**: Extract `{family}` and `{platform}` from $ARGUMENTS.

2. **Check index.json existence**:

   a. `knowledge/{family}/{platform}/merged/index.json` **exists** - go to step 3.

   b. File **missing AND** `knowledge/{family}/{platform}/` directory **does not exist**
      (first-time setup):
      - Announce: "Knowledge not found for {family}/{platform} - running first-time bootstrap."
      - Invoke `/repo-scout {family} {platform}`
      - Invoke `/knowledge-enrich {family} {platform}`
      - Invoke `/truth-merge {family} {platform}`
      - Output: `KNOWLEDGE: BOOTSTRAPPED`
      - Stop here (calling command continues from this status).

   c. File **missing BUT** `knowledge/{family}/{platform}/` directory **exists**
      (partial or interrupted state):
      - Output: `KNOWLEDGE: STOP:partial`
      - Print: "knowledge/{family}/{platform}/merged/ is missing or incomplete.
        This may indicate an interrupted bootstrap. Run /repo-scout, /knowledge-enrich,
        and /truth-merge manually to rebuild before retrying."
      - Halt - do not proceed further.

3. **Check staleness**: Read `knowledge/{family}/{platform}/merged/model.yaml` or `index.json`:
   - If `stale_since` is not null OR `stale: true`:
     - Announce: "Knowledge for {family}/{platform} is stale - refreshing."
     - Run: `python scripts/pipeline/commands/knowledge/refresh_knowledge.py {family} {platform}`
     - Reload index.json.
     - Output: `KNOWLEDGE: REFRESHED`
     - Stop here (calling command continues from this status).

4. **Check conflicts**: Read `index.json` -> `has_conflicts`:
   - If `true`:
     - Print the contents of `knowledge/{family}/{platform}/merged/merge_conflicts.md`
     - Output: `KNOWLEDGE: WARN:conflicts`
     - Stop here (calling command continues from this status).

5. **All clear**:
   - Output: `KNOWLEDGE: READY`

> **Skill context close** — run after the last step:
> ```bash
> PYTHONPATH=scripts/pipeline .venv/Scripts/python scripts/pipeline/commands/governance/skill_context.py end --skill S-54 --status completed
> ```

## How Calling Commands Use This

**Generation commands** (new-*, page-plan, page-draft) - add as pre-condition step 1:
```
1. Run `/knowledge-bootstrap {family} {platform}` and check status:
   - `STOP:partial` -> halt (see printed message)
   - `REFRESHED` -> STOP: "Knowledge was refreshed from upstream changes. Run /knowledge-diff
     to review what changed before generating content, then re-run this command."
   - `READY`, `BOOTSTRAPPED`, or `WARN:conflicts` -> continue
```

**Validation/audit commands** (content-audit, change-guard, truth-audit, faq-generate,
batch-eval-fix, batch-remediate, cross-platform) - add as pre-condition step 1:
```
1. Run `/knowledge-bootstrap {family} {platform}` and check status:
   - `STOP:partial` -> halt (see printed message)
   - Any other status (`READY`, `BOOTSTRAPPED`, `REFRESHED`, `WARN:conflicts`) -> continue
```

## When to Use Each Knowledge Skill

| Situation | Use |
|-----------|-----|
| Before generating any content (normal use) | `/knowledge-bootstrap` - auto-detects state and dispatches |
| Force full re-extraction from the FOSS repo clone | `/knowledge-update {family} {platform} $repo_path` (S-14) - re-runs repo-scout + knowledge-enrich + truth-merge + truth-index |
| Re-generate LLM enrichment without re-scouting | `/knowledge-enrich {family} {platform}` (S-37) - calls the enrich pipeline against scout/api_surface.json; writes scout/enriched_claims.json |
| Review what changed between knowledge versions | `/knowledge-diff {family} {platform}` (S-12) - diffs current vs previous; required after REFRESHED status |
| Check staleness of content pages (post-diff) | `/stale-detect {family} {platform}` (S-13) - maps changed claims to affected pages |

**Rule of thumb**: Always start with `/knowledge-bootstrap`. Only reach for S-14 or S-37 directly when you need to force a specific layer update that bootstrap does not cover.

---

## LLM Metrics Obligation

If this skill invokes `llm.professionalize.com` directly or through `LLMRouter`,
the run carries a **metrics obligation** (METRICS-PLAN-001, `AGENTS.md §15`):

- All professionalize calls must use `ProfessionalizeClient`, `LLMRouter`, or a
  registered adapter entry in `metrics_callsite_registry.yaml`.
- Each run must capture per-call `MetricsEvent` records and aggregate them into a
  validated `MetricsRow` via `RunMetrics`.
- Default mode is **dry-run**. Live posting requires explicit owner approval and
  `AGENT_METRICS_ENDPOINT` / `AGENT_METRICS_TOKEN` set locally.
- Non-professionalize calls (Gemini, Ollama, M2M) are excluded from
  `token_usage` and `api_calls_count`.
- Metrics failures must not crash or block the parent pipeline job.
