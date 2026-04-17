<!-- CONTRACT: scripts/pipeline/remediate.py heal
     purpose: batch healing from eval report — plan, execute, verify across auto/llm/regen modes
     preconditions: content_eval JSON report exists with findings
     postcondition: auto-fixes applied; LLM queue emitted; regen queue emitted; optional verification
     idempotent: auto-fixes are idempotent; LLM/regen queues are descriptors only
     verified: 2026-04-16
-->
# S-89: Heal Batch — Batch Healing from Eval Report

**Arguments**: $ARGUMENTS
Expected format: `{eval-report-path} [--mode auto|llm|regen|all] [--dry-run] [--after-report {path}] [--json]`

## Purpose

Run the healing pipeline on a batch of findings from a content_eval report. Unlike S-40
(batch-remediate) which runs eval→triage→fix→LLM sequentially, heal-batch uses the
`HealController` to route findings through the heal policy table and dispatch to the
correct healing mode (auto, llm, regen) in a single pass.

**Relationship to other healing skills:**
- **S-26 (heal-page)**: Single-page LLM healing with 2-pass escalation. Heal-batch may
  queue S-26 invocations for LLM-mode findings.
- **S-87 (system-heal)**: Audit-driven healing with origin classification and phased
  verification. Higher-level orchestrator that may invoke heal-batch internally.
- **S-40 (batch-remediate)**: Legacy eval→fix pipeline. Heal-batch supersedes the
  deterministic fix portion and adds policy-routed LLM/regen dispatch.

## Pre-conditions

1. A content_eval JSON report exists at `{eval-report-path}` with a `findings` array.
2. `scripts/pipeline/remediate.py` is available with the `heal` subcommand.
3. `scripts/pipeline/heal_controller.py`, `heal_policy.py`, and `verify.py` are importable.

## Steps

> **Skill context gate** -- run before step 1:
> ```bash
> PYTHONPATH=scripts/pipeline .venv/Scripts/python scripts/pipeline/skill_context.py begin --skill S-89 --scope "*"
> ```

1. **Parse arguments**: Extract eval-report path and optional flags from $ARGUMENTS.

2. **Run heal subcommand**:
   ```bash
   PYTHONPATH=scripts/pipeline .venv/Scripts/python scripts/pipeline/remediate.py heal \
       {eval-report-path} \
       --mode {mode|all} \
       [--dry-run] \
       [--after-report {after-report-path}] \
       [--json]
   ```

   The `heal` subcommand performs:
   - **Plan**: Triage all findings through the heal policy table, group by heal mode
   - **Execute auto**: Run deterministic fixers on auto-group findings
   - **Execute LLM**: Emit skill invocation descriptors for llm-group findings
   - **Execute regen**: Emit regen invocation descriptors for regen-group findings
   - **Verify** (if `--after-report`): Compare before/after findings for regression detection

3. **Process LLM queue** (if mode is `llm` or `all` and queue is non-empty):
   For each item in the LLM queue, the agent invokes the referenced skill (typically
   S-21 page-enhance or S-26 heal-page) with the finding context. This step is
   **agent-executed**, not automated by the script.

4. **Process regen queue** (if mode is `regen` or `all` and queue is non-empty):
   For each item in the regen queue, the agent invokes S-74 (causal-backtrack) to
   resolve upstream dependencies before local fixes. This step is **agent-executed**.

5. **Re-evaluate** (if not `--dry-run` and fixes were applied):
   ```bash
   .venv/Scripts/python -m scripts.pipeline.content_eval evaluate \
       --files {space-separated list of healed files} \
       --format json --remediation \
       --out {after-report-path}
   ```

6. **Verify** (if re-evaluation was run):
   ```bash
   PYTHONPATH=scripts/pipeline .venv/Scripts/python scripts/pipeline/remediate.py heal \
       {eval-report-path} \
       --after-report {after-report-path} \
       --json
   ```
   Check `verification.regression_detected`. If true, investigate before committing.

7. **Report**: Review the output summary:
   - `plan`: Finding counts by heal mode
   - `auto_results`: Deterministic fixes applied
   - `llm_queue`: Findings requiring LLM skill invocation
   - `regen_queue`: Findings requiring upstream backtracking
   - `verification` (if present): Regression detection results

> **Skill context close** -- run after the last step:
> ```bash
> PYTHONPATH=scripts/pipeline .venv/Scripts/python scripts/pipeline/skill_context.py end --skill S-89 --status completed
> ```

## Post-conditions

- Auto-mode findings have deterministic fixes applied (or dry-run report generated)
- LLM-mode findings have structured invocation descriptors for agent execution
- Regen-mode findings have structured invocation descriptors with `regen_after` flags
- If `--after-report` provided: verification confirms no regressions introduced
- No-downgrade-guard is enforced by the underlying auto-fixers

## Modes

| Mode | What it does | Automated? |
|------|-------------|------------|
| `auto` | Deterministic fixers (frontmatter, structure, format) | Yes |
| `llm` | Emits skill invocation descriptors for LLM healing | Queue only |
| `regen` | Emits regen descriptors for upstream backtracking | Queue only |
| `all` | Runs all three modes | Auto + queues |

## Error Handling

| Error | Cause | Fix |
|-------|-------|-----|
| `No findings in report` | Empty or malformed eval report | Re-run content_eval |
| `Policy not found` | Finding category not in heal_policy table | Check heal_policy.py; may need new entry |
| `Regression detected` | After-report shows new failures | Review verification output; revert if needed |
| `run_fixes failed` | Auto-fixer error on a specific file | Check file format; may need manual intervention |

## Related Skills

- **S-26 heal-page**: Single-page LLM healing (invoked by LLM queue items)
- **S-40 batch-remediate**: Legacy eval→fix pipeline (heal-batch supersedes auto-fix portion)
- **S-41 batch-eval-fix**: Quick eval + auto-fix only (subset of heal-batch auto mode)
- **S-74 causal-backtrack**: Upstream dependency resolution (invoked by regen queue items)
- **S-87 system-heal**: Audit-driven healing orchestrator (may invoke heal-batch)
