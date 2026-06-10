# S-79: Causal Backtrack — Resolve Upstream Dependency Failures

**Arguments**: $ARGUMENTS
Expected format: `{family} {platform} [--eval-report {path}] [--dry-run]`

- `family` — product family (e.g. `slides`)
- `platform` — platform (e.g. `net`)
- `--eval-report` — path to an `eval-*.json` from `content_eval evaluate`. If omitted, the most recent eval report for the family/platform is used.
- `--dry-run` — write evidence files but do not invoke any downstream skills.

## Purpose

When a content page receives a WARN because a linked target does not exist or uses the wrong
URL format (`cause_class: UPSTREAM_MISSING` or `cause_class: BAD_LINK_FORMAT`), this skill
traces the broken link back to its upstream cause, determines the correct remediation, and
routes control to the responsible skill.

Implements the **causal backtracking and forward replay** system defined in AGENTS.md §6c.

**Do not use for**: content quality issues unrelated to missing upstream pages (use S-26 or S-21).

## Trigger

Activate when `content_eval` reports findings with:
- `cause_class: UPSTREAM_MISSING` — a linked page/section does not exist
- `cause_class: BAD_LINK_FORMAT` — a link uses an incorrect URL format

## Steps

1. **Load eval report**: Read `{eval-report-path}` or find the most recent eval report under `reports/`.

2. **Extract dependency failures**: Filter findings to `cause_class IN [UPSTREAM_MISSING, BAD_LINK_FORMAT]`.

3. **For each failure, trace the upstream cause**:
   - Extract the broken link target from the finding
   - Determine whether the target is: a page that doesn't exist, a section that doesn't exist, or a URL format mismatch
   - Read `knowledge/{family}/{platform}/merged/model.yaml` to check if the target capability is known

4. **Classify each failure**:

   | Failure type | Root cause | Responsible skill |
   |---|---|---|
   | Missing index page (`_index.md`) | Scaffolding not run | S-74 (new-kb-index), S-75 (new-docs-index), or S-76 (new-reference-index) |
   | Missing content page | Page generation not run | S-19 (page-draft) or appropriate generation skill |
   | Wrong URL format | Link pattern mismatch | S-78 (manual-edit) with `--scope body-wording` |
   | Missing capability in knowledge | Knowledge incomplete | S-12 (knowledge-diff) → S-14 (knowledge-update) |

5. **Route to responsible skill**:
   - For each failure, emit a directive:
     ```
     ROUTE: {family}/{platform} failure at {source-page}
       Cause: {UPSTREAM_MISSING | BAD_LINK_FORMAT}
       Target: {broken-link}
       Action: invoke {skill-id} ({skill-name}) {args}
     ```
   - If `--dry-run`: emit directives only, do not invoke skills.
   - If not dry-run: invoke each responsible skill in dependency order.

6. **Forward replay verification**:
   After all upstream fixes are applied, re-run content_eval on the original failing pages:
   ```bash
   python -m scripts.pipeline.content_eval evaluate --files {source-pages} --format json
   ```
   Verify that the `UPSTREAM_MISSING`/`BAD_LINK_FORMAT` findings are resolved.

7. **Summary report**:
   ```
   CAUSAL BACKTRACK — {family}/{platform}
   Findings processed: N
   Failures classified: N
     UPSTREAM_MISSING: N
     BAD_LINK_FORMAT:  N
   Skills invoked: {list}
   Forward replay: PASS | FAIL | SKIPPED (dry-run)
   ```

## Post-conditions

- All `UPSTREAM_MISSING` failures have upstream pages created
- All `BAD_LINK_FORMAT` failures have link formats corrected
- Forward replay confirms original failing pages now pass

## Error handling

| Error | Action |
|-------|--------|
| No eval report found | Prompt operator to run `content_eval evaluate` first |
| No UPSTREAM_MISSING/BAD_LINK_FORMAT findings | Report: "No causal failures found — use other skills for other failure types" |
| Responsible skill invocation fails | Log failure; continue with remaining failures; report at end |
| Knowledge model stale | Halt: run S-12 + S-14 first |
