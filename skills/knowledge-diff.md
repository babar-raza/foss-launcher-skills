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
   First, attempt to enumerate changed files between the stored SHA and current HEAD:
   ```bash
   git -C {repo-path} log --name-only {old_sha}..HEAD
   ```
   **If this command fails** (non-zero exit, typically `fatal: Invalid revision range` or
   `fatal: bad object`), the stored `repo_sha` is not reachable in the current git history —
   this is the **ORPHANED_SHA** case. It happens when the upstream FOSS repository was
   force-pushed, rebased, or re-initialized. Do not treat this as a tool error; it is a
   distinct, expected outcome that Step 5 must classify explicitly.

   If the git log succeeds, read the changed file list to classify impact. Otherwise, classify
   by file-type heuristic on the sha diff:
   - Source files (.py, .cs, .java, .ts, .js, .cpp, .h) → API surface may have changed
   - Test files → examples may have changed
   - Manifest files (pyproject.toml, package.json, .csproj) → version/deps may have changed
   - README → descriptions may have changed

   If `knowledge/{family}/{platform}/merged/knowledge_delta.json` exists from a prior refresh
   cycle, prefer it over the heuristic above when the git log succeeded.

4a. **ORPHANED_SHA fallback — API surface comparison**:
   When Step 4 detects an orphaned SHA, git history cannot answer "what changed" — fall back
   to comparing the last-known API surface against the FOSS repo's current state:
   ```python
   import json
   from pathlib import Path

   old_surface_path = Path("knowledge/{family}/{platform}/merged/api_surface.json")
   old_classes = {c["name"] for c in json.loads(old_surface_path.read_text(encoding="utf-8"))}
   ```
   Then run `/repo-scout {family} {platform}` against the current HEAD to produce a fresh
   `scout/api_surface.json`, and diff the class name sets:
   ```python
   new_surface_path = Path("knowledge/{family}/{platform}/scout/api_surface.json")
   new_classes = {c["name"] for c in json.loads(new_surface_path.read_text(encoding="utf-8"))}
   added = new_classes - old_classes
   removed = old_classes - new_classes
   ```
   - If `removed` is empty (additions only, or identical) → treat as **MEDIUM** impact;
     proceed to `/knowledge-update {family} {platform}`.
   - If `removed` is non-empty (classes disappeared or the surface was restructured) →
     treat as **HIGH** impact; halt and report to the operator before proceeding. Do not
     run `/page-retire` from this diff alone — a shrunken class-name set from an orphaned
     SHA is not reliable evidence that content should be retired; it may mean the scout
     needs re-tuning as easily as it may mean the API genuinely shrank. Verify manually.
   - Record the finding in the diff report (see Output below) — do not silently resolve
     the orphaned SHA by treating it as LOW impact or skipping stale_since.

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

   **ORPHANED_SHA case**: always set `stale_since` (using the same guard above), regardless
   of whether Step 4a classified the result as MEDIUM or HIGH — an orphaned SHA means the
   stored knowledge cannot be confirmed current against upstream, so it must not be reported
   as fresh. Also set `orphaned_sha: true` in the same model.yaml write:
   ```python
   model["orphaned_sha"] = True
   ```
   `orphaned_sha` stays `true` until a subsequent `/knowledge-update` run completes and
   re-promotes the model — at that point `promote.py` should clear the flag along with
   `stale_since`, since the new promotion re-establishes a git-reachable baseline SHA.

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
Impact: HIGH|MEDIUM|LOW|ORPHANED_SHA

## Changed files
- src/scene.py (source) → HIGH impact
- tests/test_load.py (test) → MEDIUM impact

## Recommendation
Re-run `/knowledge-update {family} {platform}` to update knowledge
stale_since set to {today} in merged/model.yaml (HIGH/MEDIUM impact only)
```

For the ORPHANED_SHA case, the report instead includes:
```
# Knowledge Diff: {family}/{platform}
Stored SHA: {old_sha}
Current SHA: {new_sha}
Impact: ORPHANED_SHA

## ORPHANED_SHA — git history diff unavailable
Stored SHA {old_sha} is not reachable from current HEAD ({new_sha}).
Likely cause: upstream force-push, rebase, or repository re-initialization.
Fell back to API surface comparison (Step 4a):
  Classes added:   {N}
  Classes removed: {M}
  Resolved impact: MEDIUM (additions only) | HIGH (removals — halt for review)

## Recommendation
{MEDIUM: Re-run /knowledge-update {family} {platform}}
{HIGH: Do NOT run /knowledge-update or /page-retire automatically. Review the
 removed class list manually before proceeding — the FOSS repository's history
 was rewritten and the scope of change cannot be confirmed from git alone.}
stale_since and orphaned_sha:true set in merged/model.yaml regardless of outcome.
```

## Post-conditions
- Diff report is printed to output with impact classification (HIGH/MEDIUM/LOW/ORPHANED_SHA).
- If HIGH or MEDIUM impact: `stale_since` is auto-set in `merged/model.yaml` to today's date;
  recommendation to run S-14 (knowledge-update) is included in the report.
- If ORPHANED_SHA: both `stale_since` and `orphaned_sha: true` are set in `merged/model.yaml`,
  regardless of the Step 4a-resolved impact level. `orphaned_sha` is only cleared by a
  subsequent successful `/knowledge-update` promotion.
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
