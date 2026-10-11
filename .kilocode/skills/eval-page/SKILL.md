<!-- CONTRACT: scripts/pipeline/content_eval/cli.py evaluate
     purpose: evaluate page content and produce a quality grade (A-F)
     preconditions: target file exists under content/; knowledge model available for full evaluation
     postcondition: grade assigned with findings report and remediation plan; no file modifications
     idempotent: yes — deterministic evaluators produce same grade for same input
     verified: 2026-04-11
-->
---
name: eval-page
description: >
  Evaluate page content and produce a quality grade
args: "{relative-file-path}"
---

> Cross-skill references like `/knowledge-bootstrap` refer to sibling skills in this directory.

# S-25: Eval Page — Evaluate Page and Produce Grade

**Arguments**: $ARGUMENTS
Expected format: `{relative-file-path}` — e.g. `content/docs.aspose.org/en/3d/python/developer-guide/rendering.md`

## Purpose
Evaluate a content page using the content_eval pipeline and produce a letter grade (A-F). This is the primary quality gate for deciding whether a page needs enhancement (S-21) or healing (S-26).

## Batch mode

For batch evaluation of all pages in a product, use S-51 (content-eval):
```bash
.venv/Scripts/python -m scripts.pipeline.content_eval evaluate {family} {platform} --format json --remediation
```

## Pre-conditions
1. The file at `{relative-file-path}` exists under `content/`
2. `scripts/pipeline/content_eval` module is available
3. Detect `{family}` and `{platform}` from the file path
4. `knowledge/{family}/{platform}/merged/` should exist for full evaluation (degraded mode without it)

## Steps

> **Skill context gate** — run before step 1:
> ```bash
> PYTHONPATH=scripts/pipeline .venv/Scripts/python scripts/pipeline/commands/governance/skill_context.py begin --skill S-25 --scope "*"
> ```


1. **Parse arguments**: Extract file path from $ARGUMENTS.

2. **Run content_eval**:
   ```bash
   .venv/Scripts/python -m scripts.pipeline.content_eval evaluate --files {relative-file-path} --format json --remediation
   ```

2b. **Run smoke test** (all platforms — Python, Java, C#, TypeScript, C++, Rust):
   ```bash
   .venv/Scripts/python scripts/pipeline/commands/diagnostics/smoke_test.py --files {relative-file-path}
   ```
   - Exit code 2 (FAIL): count each failing block as one additional FAIL finding
   - Exit code 1 (WARN): count each warning block as one additional WARN finding
   - Exit code 0 (PASS): no additional findings from smoke test
   - If smoke_test.py not found: skip silently (tool not yet installed)

3. **Parse output**: Extract findings categorized by severity:
   - **FAIL**: Critical issues that must be fixed
   - **WARN**: Issues that should be fixed
   - **INFO**: Suggestions for improvement

4. **Count findings**:
   - `fail_count` = number of FAIL findings
   - `warn_count` = number of WARN findings

5. **Assign grade** based on finding counts:

   | Grade | Criteria |
   |-------|----------|
   | A | 0 FAIL, 0-2 WARN |
   | B | 0 FAIL, 3-5 WARN |
   | C | 0 FAIL, 6+ WARN; or 1-2 FAIL |
   | D | 3-5 FAIL |
   | F | 6+ FAIL, or any critical finding (forbidden claim used, wrong platform code) |

6. **Determine next action**:
   - Grade A: Ready for publication
   - Grade B: Minor polish — run S-21 (page-enhance) optionally
   - Grade C: Run S-21 (page-enhance)
   - Grade D: Run S-26 (heal-page)
   - Grade F: Escalate to human review

7. **Output evaluation report**:
   ```
   EVAL PAGE — {file-path}
   Product: {family}/{platform}

   FINDINGS
     FAIL ({fail_count}):
       [{evaluator}] {description}
       ...
     WARN ({warn_count}):
       [{evaluator}] {description}
       ...

   GRADE: {letter} ({fail_count} FAIL, {warn_count} WARN)

   REMEDIATION PLAN (if grade < A):
     Priority 1 (FAIL fixes):
       - {specific fix instruction}
     Priority 2 (WARN fixes):
       - {specific fix instruction}

   NEXT STEP: {recommendation}
   ```

> **Skill context close** — run after the last step:
> ```bash
> PYTHONPATH=scripts/pipeline .venv/Scripts/python scripts/pipeline/commands/governance/skill_context.py end --skill S-25 --status completed
> ```

## Post-conditions
- Evaluation report is printed with grade and findings
- Grade is one of A, B, C, D, F
- Remediation plan is included for grades below A
- Next step recommendation references the correct downstream skill
- No file modifications made (read-only skill)

## Error handling
- If content_eval module is not available, fall back to running `python scripts/pipeline/commands/content/audit.py --files {path}` for API accuracy check only, and assign grade based on audit results alone
- If knowledge model is missing, note in output that evaluation is partial (API accuracy and evidence checks will be limited)
- If the file does not exist, abort with clear message

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
