---
# Governance child document — ported from aspose.org
# Source: AGENTS.md §6c
# Ported: 2026-05-20 (parity migration)
# ID mapping: aspose.org skill IDs remapped to foss-launcher IDs per docs/id-mapping.md
---

# Causal Backtracking Protocol (added 2026-04-03)

### Principle

A page grade is only **final** when all evaluation findings are caused by **local content defects** that the page itself can fix. If any finding has `cause_class: UPSTREAM_MISSING` or `cause_class: BAD_LINK_FORMAT`, the grade is **provisional** and MUST NOT be treated as a terminal quality judgment. The system must trace the problem to its upstream cause, invoke the responsible skill, and replay evaluation before writing a final grade.

This is **required system behavior** — not an optional enhancement.

### When causal backtracking activates

Causal backtracking MUST activate whenever:
- A `content_eval` evaluation produces findings with `cause_class: UPSTREAM_MISSING` or
  `cause_class: BAD_LINK_FORMAT`.
- These findings appear in the triage result's `upstream_blocked` list.
- `/batch-remediate` is run and `triage.upstream_blocked` is non-empty.

### Required action sequence

1. **Do not write a final grade** while `cause_class=UPSTREAM_MISSING` findings exist.
   Set `grade_final: false` and `grade_stale_reason: upstream_missing`.

2. **Invoke S-79 (causal-backtrack):**
   ```
   /causal-backtrack {family} {platform} [--eval-report {path}]
   ```

3. **Read the action plan** from `reports/dependency-backtrack/{run-id}/backtrack-summary.md`.

4. **Execute action items** in order:
   - `GENERATE` → run S-67 or S-60 for missing reference pages.
   - `CORRECT_LINK` → run S-78 with `--scope body-wording` on source pages.
   - `ESCALATE` → write to human queue; grade remains stale.

5. **Replay evaluation** on all pages listed in `replay_plan`.

6. **Write final grade** only after replay shows zero `UPSTREAM_MISSING` findings.

### Grade policy under this protocol

| Finding state after replay | grade_final | Rule |
|---------------------------|-------------|------|
| Zero UPSTREAM_MISSING findings | `true` | Write final grade |
| UPSTREAM_MISSING findings remain, depth < 3 | `false` | Recurse S-79 |
| UPSTREAM_MISSING findings remain, depth >= 3 | `false` | ESCALATE; human queue |
| Verdict was ESCALATE | `false` | Human queue; grade stays stale |
| Only LOCAL_DEFECT findings | `true` | Write final grade (page has fixable defects) |

### Cause classification taxonomy

| cause_class | Meaning | Default action |
|-------------|---------|----------------|
| `LOCAL_DEFECT` (default) | Content the page itself must fix | Existing triage flow |
| `UPSTREAM_MISSING` | Link target absent from file system | S-79 → DependencyVerifier |
| `BAD_LINK_FORMAT` | Target exists but URL casing/slug is wrong | S-79 → S-78 CORRECT_LINK |
| `KNOWLEDGE_STALE` | Finding depends on stale knowledge | Hard stop → S-12 → S-14 |
| `PREREQUISITE_ABSENT` | Evaluation precondition not met | Hard stop; fix prerequisites |

### Evidence requirements

All S-79 runs MUST produce the following files (written before any skill is invoked):
- `reports/dependency-backtrack/{run-id}/cause-classification.json`
- `reports/dependency-backtrack/{run-id}/dependency-verification.json`
- `reports/dependency-backtrack/{run-id}/remediation-decision.json`
- `reports/dependency-backtrack/{run-id}/invoked-skill-record.json`
- `reports/dependency-backtrack/{run-id}/replay-plan.json`
- `reports/dependency-backtrack/{run-id}/revalidation-report.json`
- `reports/dependency-backtrack/{run-id}/final-grade-decision.json`

If any action escalates to human:
- `reports/dependency-backtrack/needs-human-{YYYYMMDD}.md`

### Safety bounds

- `MAX_BACKTRACK_DEPTH = 3` — at depth >= 3, ESCALATE unconditionally.
- Cycle detection: if the same target URL is encountered twice in one run, skip it and
  write `cycle-detected.json`. Do not recurse infinitely.
- S-67/S-60 are idempotent: re-running never overwrites existing pages.
- S-78 edits only the URLs specified in `--intent`; it never rewrites other content.

### Prohibition

It is **prohibited** to:
- Write `grade_final: true` on a page that still has `cause_class=UPSTREAM_MISSING` findings.
- Edit the source page's link to a non-existent target to "remove the warning."
- Skip S-79 and proceed directly to local triage when `upstream_blocked` is non-empty.
- Treat a grade B caused entirely by broken link WARNs as a terminal content defect.
