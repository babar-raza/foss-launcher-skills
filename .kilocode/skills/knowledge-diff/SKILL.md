---
name: knowledge-diff
id: S-12
description: >
  Detect changes in the upstream FOSS repository since the last knowledge
  extraction by comparing git SHAs and knowledge artifacts.
args: "{family} {platform} {repo-path}"
---

> Cross-skill references like `/knowledge-bootstrap` refer to sibling skills in this directory.

# S-12: Knowledge Diff — Detect Upstream Changes

**Arguments**: $ARGUMENTS
Expected format: `{family} {platform} {repo-path}`

## Resolving `{repo-path}`

First, update the local clone to fetch any upstream changes, then resolve the path:
```bash
.venv/Scripts/python -c "from scripts.pipeline.core.clone_cache import update_clone; update_clone('{family}', '{platform}')"
repo_path=$(.venv/Scripts/python scripts/pipeline/core/clone_cache.py resolve {family} {platform})
```
Then invoke this skill as: `/knowledge-diff {family} {platform} $repo_path`

Override the cache root with `ASPOSE_CLONE_CACHE=/path/to/cache` if needed.

## Purpose
Detect changes in the upstream FOSS repository since the last knowledge extraction by comparing
git SHAs and knowledge artifacts. Uses the local clone cache — automatically fetches upstream
before SHA comparison so detection is never blind.

## Pre-conditions
1. `knowledge/{family}/{platform}/merged/model.yaml` must exist with `repo_sha`
2. The repo at `{repo-path}` must be a git repository (managed by `core/clone_cache.py`)

## Steps

> **Skill context gate** — run before step 1:
> ```bash
> PYTHONPATH=scripts/pipeline .venv/Scripts/python scripts/pipeline/commands/governance/skill_context.py begin --skill S-12 --scope "*"
> ```


1. **Update clone and get current SHA**:
   ```python
   from scripts.pipeline.core.clone_cache import update_clone, clone_head_sha
   update_clone('{family}', '{platform}')   # git fetch --depth=1 + reset --hard origin/HEAD
   current_sha = clone_head_sha('{family}', '{platform}')
   ```
   If `update_clone()` returns `None` (fetch failed), proceed with the existing local clone HEAD
   and note that the comparison may not reflect the latest upstream state.

2. **Get stored SHA**: Read `repo_sha` from `knowledge/{family}/{platform}/merged/model.yaml`

3. **Compare**: If SHAs match, report "no changes" and exit cleanly — no further action needed.

4. **Classify impact from knowledge artifacts**:
   If `knowledge/{family}/{platform}/merged/knowledge_delta.json` exists from a prior refresh
   cycle, read it to classify impact. Otherwise, classify by file-type heuristic on the sha diff:
   - Source files (.py, .cs, .java, .ts, .js, .cpp, .h) → API surface may have changed
   - Test files → examples may have changed
   - Manifest files (pyproject.toml, package.json, .csproj) → version/deps may have changed
   - README → descriptions may have changed

5. **Classify impact**:
   - HIGH: Source files in package root changed → re-scout needed
   - MEDIUM: Test/example files changed → snippets may need update
   - LOW: Only docs/config changed → cosmetic

6. **Auto-set stale_since for HIGH/MEDIUM impact**:
   When impact is HIGH or MEDIUM, set `stale_since` in `knowledge/{family}/{platform}/merged/model.yaml`
   to today's date. This marks the product as requiring a refresh — no manual operator step required.
   ```python
   import yaml
   from datetime import date
   model_path = "knowledge/{family}/{platform}/merged/model.yaml"
   with open(model_path) as f:
       model = yaml.safe_load(f)
   if model.get("stale_since") is None:
       model["stale_since"] = str(date.today())
       with open(model_path, "w") as f:
           yaml.safe_dump(model, f)
   ```
   LOW impact: do NOT set stale_since; just report.

7. **Report**: Write diff report with recommendations

> **Skill context close** — run after the last step:
> ```bash
> PYTHONPATH=scripts/pipeline .venv/Scripts/python scripts/pipeline/commands/governance/skill_context.py end --skill S-12 --status completed
> ```

## Output
```
# Knowledge Diff: {family}/{platform}
Stored SHA: {old_sha}
Current SHA: {new_sha}
Impact: HIGH|MEDIUM|LOW

## Changed files
- src/scene.py (source) → HIGH impact
- tests/test_load.py (test) → MEDIUM impact

## Recommendation
Re-run `/knowledge-update {family} {platform}` to update knowledge
stale_since set to {today} in merged/model.yaml (HIGH/MEDIUM impact only)
```

## Post-conditions
- Diff report is printed to output with impact classification (HIGH/MEDIUM/LOW).
- If HIGH or MEDIUM impact: `stale_since` is auto-set in `merged/model.yaml` to today's date;
  recommendation to run S-14 (knowledge-update) is included in the report.
- If no changes (SHAs match): skill exits cleanly with "no changes" message; no further action needed.
- The stored `repo_sha` in `merged/model.yaml` is NOT modified by this skill — it is read-only.
  SHA update only happens in S-14 (knowledge-update) after re-scouting completes.
- `update_clone()` is called before SHA comparison — change detection is never blind to upstream commits.

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
