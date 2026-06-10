# S-94: Heal Batch — Batch Healing from Eval Report

**Arguments**: $ARGUMENTS
Expected format: `{eval-report-path} [--mode auto|llm|regen|all] [--dry-run] [--after-report {path}] [--json]`

## Purpose

Run the healing pipeline on a batch of findings from a content_eval report. Uses the
HealController to route findings through the heal policy table and dispatch to the
correct healing mode (auto, LLM, regen) in a single pass.

**Relationship to other healing skills:**
- **S-26 (heal-page)**: Single-page LLM healing with 2-pass escalation. Heal-batch may queue S-26 invocations for LLM-mode findings.
- **S-40 (batch-remediate)**: Legacy eval→fix pipeline. Heal-batch supersedes the deterministic fix portion and adds policy-routed LLM/regen dispatch.

## Pre-conditions

1. A content_eval JSON report exists at `{eval-report-path}` with a `findings` array.
2. `knowledge/{family}/{platform}/merged/model.yaml` exists with `stale_since: null` for each product in scope.

## Healing Modes

| Mode | What it does |
|------|-------------|
| `auto` | Script-driven deterministic fixes (claim ID updates, provenance fixes, structural corrections) |
| `llm` | LLM-driven prose/content fixes — queues S-26 (heal-page) invocations |
| `regen` | Full page regeneration for grade D/F pages — queues appropriate generation skill |
| `all` | Run all three modes in order: auto → llm → regen |

## Steps

1. **Parse arguments**: Extract report path, mode, and flags.

2. **Load eval report**: Read `{eval-report-path}`. Validate it contains a `findings` array.

3. **Group findings by heal mode** using the heal policy table:

   | Finding type | Heal mode |
   |---|---|
   | Stale claim ID (`CLM-` format changed) | auto |
   | Missing provenance block | auto |
   | Structural frontmatter issue | auto |
   | Broken evidence citation | auto |
   | Low evidence depth (grade B→A improvement) | llm |
   | Incorrect prose claim | llm |
   | Missing section | llm |
   | Grade D or F (multiple FAIL findings) | regen |

4. **Auto mode fixes** (if `--mode auto` or `--mode all`):
   ```bash
   python scripts/pipeline/commands/content/remediate.py heal \
     --report {eval-report-path} \
     --mode auto \
     [--dry-run]
   ```
   Report: `Auto-fixed: N findings across M files`

5. **LLM mode — queue S-26 invocations** (if `--mode llm` or `--mode all`):
   For each LLM-mode finding, emit a queued directive:
   ```
   QUEUE: /heal-page {path} --scope {finding_type} --hint "{finding_description}"
   ```
   If not `--dry-run`: invoke each S-26 in sequence.

6. **Regen mode — queue generation skills** (if `--mode regen` or `--mode all`):
   For each regen-mode page, determine and emit the appropriate generation skill.
   If not `--dry-run`: invoke each generation skill in sequence.

7. **Post-healing verification** (if `--after-report {path}` or not `--dry-run`):
   Re-run content_eval on all touched files:
   ```bash
   python -m scripts.pipeline.content_eval evaluate --files {touched-files} --format json
   ```
   Compare before/after grades.

8. **Summary report**:
   ```
   === HEAL BATCH ===
   Report:   {eval-report-path}
   Mode:     {mode}
   Dry-run:  {yes|no}

   Findings processed: N
     Auto-mode:  N
     LLM-mode:   N
     Regen-mode: N

   Auto fixes applied: N (dry-run: would apply N)
   LLM jobs queued:    N (dry-run: preview only)
   Regen jobs queued:  N (dry-run: preview only)

   Grade changes (verified):
     Improved: N files
     Unchanged: N files
     Regressed: N files (investigate)
   ```

## Post-conditions

- Auto fixes applied to all auto-mode findings (or queued if `--dry-run`)
- LLM jobs queued for all LLM-mode findings
- Regen jobs queued for all regen-mode pages
- No page grade decreased (regressions reported)

## Error handling

| Error | Action |
|-------|--------|
| Report file not found | FAIL with helpful message |
| Knowledge model stale for a product | Skip that product; report warning |
| Auto fix causes FAIL | Revert that file; report as error |
| S-26 invocation fails | Log; continue with remaining LLM jobs |
