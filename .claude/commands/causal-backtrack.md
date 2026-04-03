<!-- CONTRACT: scripts/pipeline/backtrack_controller.py + scripts/pipeline/dependency_resolver.py -->
# S-74: Causal Backtrack — Resolve Upstream Dependency Failures

**Skill ID:** S-74
**Trigger:** Any evaluation finding with `cause_class: UPSTREAM_MISSING` or
`cause_class: BAD_LINK_FORMAT` — i.e., when a page receives a WARN because a
linked target does not exist or uses the wrong URL format.

**Arguments:**
```
/causal-backtrack {family} {platform} [--eval-report {path}] [--dry-run]
```

- `family` — product family (e.g. `slides`)
- `platform` — platform (e.g. `net`)
- `--eval-report` — path to an `eval-*.json` from `content_eval evaluate`. If omitted, the
  most recent eval report for the family/platform is used.
- `--dry-run` — write evidence files but do not invoke any downstream skills.

---

## Purpose

The default pipeline behavior writes a grade (e.g. B) when evaluation finds broken links.
This skill prevents that: it **traces the broken link back to its upstream cause**, determines
the correct remediation, and routes control to the responsible stage/skill.

This implements the **causal backtracking and forward replay** system defined in AGENTS.md §6c.

---

## When to Use

Invoke this skill:
1. Automatically — as a pre-triage step in `/batch-remediate` when the triage result
   contains `upstream_blocked` items.
2. Manually — when a page is stuck at grade B/C due to link WARNs and you want the
   system to investigate the root cause rather than edit the page.

Do NOT invoke this skill:
- For findings without `cause_class: UPSTREAM_MISSING|BAD_LINK_FORMAT`.
- When knowledge is stale (`stale_since != null`). Run S-12 → S-14 first.

---

## Procedure

### Step 1 — Locate or run evaluation

1. If `--eval-report` is provided, load that report.
2. Otherwise, run: `python -m scripts.pipeline.content_eval evaluate {family} {platform}`
   and use the latest report from `reports/content_eval/`.
3. Filter findings to those with `cause_class` in `{UPSTREAM_MISSING, BAD_LINK_FORMAT}`.
4. If no such findings: print `SKIP: no upstream-blocked findings` and stop.

### Step 2 — Run BacktrackController

```bash
.venv/Scripts/python scripts/pipeline/backtrack_controller.py \
    --eval-report {eval-report-path} \
    --family {family} \
    --platform {platform} \
    [--dry-run]
```

The controller writes all evidence to `reports/dependency-backtrack/{run-id}/`.
Read the output `backtrack-summary.md` to understand the action plan.

### Step 3 — Execute action items

For each action item in the backtrack report's `action_items` array:

**If action_type == GENERATE:**
```
/batch-reference {family} {platform} --classes {target_slug}
```
Or for a single class:
```
/new-reference-page {family} {platform} {ClassName}
```
After generation: verify the file exists at
`content/reference.aspose.org/en/{family}/{platform}/{ClassName}.md`.

**If action_type == CORRECT_LINK:**
For each source page listed:
```
/manual-edit {source-page-path} \
    --scope body-wording \
    --intent "Correct reference URL: replace `{wrong_url}` with `{correct_url}`"
```

**If action_type == ESCALATE:**
The broken link cannot be automatically resolved. The page's grade is marked
`grade_final: false` with `grade_stale_reason: escalated_to_human`. No further
automatic action is taken. The source page is added to the human queue at
`reports/dependency-backtrack/needs-human-{YYYYMMDD}.md`.

### Step 4 — Write invoked-skill record

After executing each action item, append to
`reports/dependency-backtrack/{run-id}/invoked-skill-record.json`:
```json
{
  "skill": "{skill_id}",
  "args": "{skill_args}",
  "source_pages": [...],
  "target_url": "{url}",
  "completed_at": "{ISO timestamp}",
  "result": "success | partial | failed"
}
```

### Step 5 — Replay evaluation on affected pages

For each page in the backtrack report's `replay_plan`:
```bash
.venv/Scripts/python -m scripts.pipeline.content_eval evaluate {page-path}
```
Write results to `reports/dependency-backtrack/{run-id}/revalidation-report.json`.

Verify: the count of `cause_class=UPSTREAM_MISSING` findings on these pages is now 0.
If upstream-missing findings remain AND recursion depth < 3:
→ Re-invoke this skill with `--depth {depth+1}`.
If depth >= 3: ESCALATE — write to human queue, stop.

### Step 6 — Update grades

For each page in the replay plan where revalidation passes (0 UPSTREAM_MISSING findings):
```bash
.venv/Scripts/python scripts/pipeline/grade_writer.py {page-path} \
    --grade {new-grade} --grade-final true
```
Or via the Python API:
```python
write_grade(
    filepath=Path(page_path),
    grade=new_grade,
    model_sha=knowledge_sha,
    grade_final=True,   # grade is now final — all dependencies resolved
)
```

For pages with ESCALATE verdicts, set `grade_final: false`:
```python
write_grade(
    filepath=Path(page_path),
    grade=current_grade,
    grade_final=False,
    grade_stale_reason="escalated_to_human",
    grade_stale_targets=["reference.aspose.org/slides/net/SomeMissingClass"],
)
```

### Step 7 — Write final-grade-decision record

Append to `reports/dependency-backtrack/{run-id}/final-grade-decision.json`:
```json
{
  "page": "{path}",
  "prior_grade": "{A|B|C|D|F}",
  "new_grade": "{A|B|C|D|F}",
  "grade_final": true|false,
  "grade_stale_reason": "{reason or empty}",
  "trigger_chain": ["S-74", "{action_skill}", "content_eval", "grade_writer"],
  "decided_at": "{ISO timestamp}"
}
```

---

## Evidence Files

All files written to `reports/dependency-backtrack/{family}-{platform}-{YYYYMMDD-HHMMSS}/`:

| File | Written by |
|------|-----------|
| `backtrack-report.json` | BacktrackController |
| `backtrack-summary.md` | BacktrackController |
| `cause-classification.json` | BacktrackController |
| `dependency-verification.json` | BacktrackController + DependencyVerifier |
| `remediation-decision.json` | BacktrackController |
| `invoked-skill-record.json` | Agent (Step 4) |
| `generated-artifact-manifest.json` | S-60/S-62 (via attach_evidence.py) |
| `revalidation-report.json` | Agent (Step 5) |
| `final-grade-decision.json` | Agent (Step 7) |

If escalated: `reports/dependency-backtrack/needs-human-{YYYYMMDD}.md`

---

## Hard Stops

- If `model.yaml.stale_since != null`: HALT. Run S-12 → S-14 first.
- If S-01 path-guard returns DENY on any generated file: skip that file, log error.
- If `backtrack_depth >= 3`: ESCALATE unconditionally, write human queue entry.
- If the same target URL appears twice in the visited set: HALT recursion on that URL,
  write `cycle-detected.json`, continue with others.

---

## Grade Policy

| Condition | grade_final | Action |
|-----------|-------------|--------|
| All upstream findings resolved after replay | `true` | Write final grade post-replay |
| Some upstream findings still present after replay | `false` | Mark stale; recurse or escalate |
| Verdict ESCALATE (no auto-fix possible) | `false` | Mark stale; write human queue |
| All findings are LOCAL_DEFECT after replay | `true` | Write final grade |

**Key principle:** A grade is only written as `grade_final: true` after a complete
replay evaluation shows zero `UPSTREAM_MISSING` findings on the page.

---

## Dependency Activation Rule (DAR)

This skill depends on:
- Knowledge model current (`stale_since == null`) — verify before running
- `api_surface.json` present at `knowledge/{family}/{platform}/merged/` — required by DependencyVerifier
- S-01 (path-guard) available — checked for each generated file

This skill is a prerequisite for:
- Final grade assignment on any page with `cause_class=UPSTREAM_MISSING` findings
