<!-- CONTRACT: agent-executed
     purpose: heal a low-quality page by applying targeted fixes for each FAIL finding
     preconditions: eval-page grade D or F available; knowledge model current
     postcondition: page quality improved (grade >= prior) or routed to S-90 for governed inspection
     idempotent: no — LLM-generated fixes vary between invocations
     verified: 2026-04-11
     depends_on: [S-25, S-54]
-->
# S-26: Heal Page — Heal Low-Quality Page

**Arguments**: $ARGUMENTS
Expected format: `{relative-file-path}` — e.g. `content/docs.aspose.org/en/3d/python/developer-guide/rendering.md`

## Purpose
Heal a page that received grade D or below from S-25 (eval-page). Applies targeted fixes for each FAIL finding, then re-evaluates. Escalates to human if grade does not improve after 2 attempts.

## Pre-conditions
1. S-25 (eval-page) has been run and the page received grade D or F
2. The file at `{relative-file-path}` exists under `content/`
3. Detect `{family}` and `{platform}` from the file path
4. `knowledge/{family}/{platform}/merged/` exists with `claims.json`, `api_surface.json`
5. Knowledge freshness is auto-checked via `refresh_knowledge.py` in Step 2

## Steps

> **Skill context gate** — run before step 1:
> ```bash
> PYTHONPATH=scripts/pipeline .venv/Scripts/python scripts/pipeline/commands/governance/skill_context.py begin --skill S-26 --scope "*"
> ```


1. **Parse arguments**: Extract file path from $ARGUMENTS.

2. **Auto-refresh knowledge**: Before loading any knowledge artifacts, ensure they are current.
   Invoke S-14 (knowledge-update) via its underlying script:
   ```bash
   .venv/Scripts/python scripts/pipeline/commands/knowledge/refresh_knowledge.py {family} {platform}
   ```
   - If it prints "refreshed": knowledge was stale and has been rebuilt from the clone cache.
   - If it prints "current": no action needed.
   - If clone cache is missing: warn but continue with existing knowledge artifacts.

3. **Load evaluation report**: Retrieve S-25 output for this page. If not available, run S-25 first:
   ```bash
   .venv/Scripts/python -m scripts.pipeline.content_eval evaluate --files {relative-file-path} --format json --remediation
   ```
   If grade is C or above, report that healing is not needed and exit.

4. **Load knowledge artifacts**:
   - Read `knowledge/{family}/{platform}/merged/claims.json`
   - Read `knowledge/{family}/{platform}/merged/api_surface.json`
   - Read `knowledge/{family}/{platform}/merged/formats.json`
   - Read `knowledge/{family}/{platform}/merged/limitations.md`
   - Read `knowledge/{family}/{platform}/snippets/` for code replacements

5. **Read the current page content**.

6. **Healing pass 1** — apply targeted fixes for each FAIL finding:

   | Finding type | Fix strategy |
   |-------------|-------------|
   | API accuracy FAIL | Replace wrong API token with correct one from `api_surface.json` |
   | Forbidden claim | Remove the sentence/paragraph containing it |
   | Wrong platform code | Replace code block with correct-platform snippet from `snippets/` |
   | Broken structure | Rebuild section following page-type template |
   | Missing frontmatter | Add required fields |
   | Placeholder text | Replace with knowledge-grounded content or remove |
   | Risk language | Rewrite with factual, evidence-backed phrasing |

7. **Update evidence frontmatter**: Refresh `claims`, `apis`, and `model_sha`.

8. **Run ground-check after pass 1**:
   ```bash
   .venv/Scripts/python scripts/pipeline/commands/content/audit.py --files {relative-file-path}
   ```

9. **Re-evaluate after pass 1**:
   ```bash
   .venv/Scripts/python -m scripts.pipeline.content_eval evaluate --files {relative-file-path} --format json
   ```

10. **Check improvement**: If grade is now C or above, persist the grade and report success:
    ```bash
    .venv/Scripts/python -m scripts.pipeline.content_eval evaluate --files {relative-file-path} --write-grade-if-policy-met
    ```
    This writes the new canonical grade via the write policy gate (WP-01) — body changed + grade improved.
    Then exit.

11. **Healing pass 2** (if still D or F): Apply more aggressive fixes:

    **Ground-check before pass 2** (TC-P3-04):
    ```bash
    .venv/Scripts/python scripts/pipeline/commands/content/audit.py --files {relative-file-path}
    ```
    If audit.py finds new FAIL findings not present in the Pass 1 report, halt and escalate
    to human review — do not proceed with aggressive rewrites until the new failures are
    understood. If audit.py is clean (no new FAILs), continue.

    **Pass 2 scope** (non-negotiable): Operates only on findings present in the
    Pass 1 report. Every edit must be traceable to a specific FAIL finding by
    line number or claim ID. If no FAIL finding justifies a proposed edit,
    invoke the agent-owned review lane (S-73 / S-90) instead of proceeding.

    **Preserve-first rule** (enforced, not advisory):
    - Do NOT modify, remove, reorder, or rewrite any section, paragraph, bullet,
      table row, code block, link, note, or navigation/reference content that has
      zero FAIL findings. This applies regardless of whether that content appears
      in claims.json or api_surface.json.
    - Sections with zero FAIL findings — including but not limited to: See Also,
      Related Links, navigation lists, manually authored notes, supplemental
      references, and appended link collections — must survive Pass 2 unchanged.
    - "No knowledge backing" is not a deletion reason.
    - "Not in claims.json" is not a deletion reason.
    - A section containing one FAIL finding is not globally failing. Preserve
      all sub-content in that section that has no associated FAIL finding.

    **Permitted actions** (FAIL-finding-scoped only):
    - For a content unit (sentence, paragraph, bullet, table row, or code block)
      that is the direct subject of a FAIL finding: rewrite it using claims and
      snippets from knowledge/, or remove it if no correct replacement exists.
      Do not extend changes to neighboring content as a side effect.
    - Rewriting an entire section requires per-unit evidence that every
      substantive unit in that section is individually tied to a separate FAIL
      finding. Provide per-unit evidence before proceeding.
    - Simplify a code example only when that specific code block is the subject
      of a FAIL finding (wrong API call, wrong platform code, unverified API token).
    - If you cannot identify a specific FAIL finding that justifies a proposed edit,
      stop the mutation and invoke the agent-owned review lane (S-73 or S-90,
      invoked by the agent on behalf of governance). Mark as BLOCKED with evidence
      if no safe agent-owned path exists.

12. **Re-evaluate after pass 2**:
    ```bash
    .venv/Scripts/python -m scripts.pipeline.content_eval evaluate --files {relative-file-path} --format json
    ```

13. **Update provenance**: After each pass that modifies body content, update the provenance mechanism:
    ```python
    from provenance import update_mechanism
    from pathlib import Path
    update_mechanism(Path("{relative-file-path}"), "heal-page")
    ```
    The `content_hash` will be normalized automatically by the pre-commit hook — do not compute or pass it here.

14. **Persist grade update**: If body changed and grade improved, persist the new canonical grade:
    ```bash
    .venv/Scripts/python -m scripts.pipeline.content_eval evaluate --files {relative-file-path} --write-grade-if-policy-met
    ```
    The write policy gate (WP-01) ensures grades are only written when body content changed and the grade actually changed (or on first grading). Do not use `--write-grade` (force mode) here.

15. **Final decision**:
    - If grade C or above: report success
    - If still D or F: **invoke S-90 (`/publish-readiness-review`)** — do not halt and
      write a generic escalation item. S-90 will inspect the page, classify the remaining
      findings, attempt further routing (additional passes via S-89 if appropriate), and
      determine whether the page requires real human escalation per §7c. S-90 is the
      governed continuation path; do not stop here.
      If S-90 also cannot resolve the grade (Grade F after 2 S-26 passes + 1 S-89 pass):
      S-90 records the real escalation with concrete reason.

15b. **Backlink compliance check** (add-only safety net — after all healing passes):
    Verify that the healed page still has a compliant aspose.com content-area backlink
    in its See Also / Related Resources section. This step is a SAFETY NET: the
    preserve-first rule (Step 11) must have already prevented any See Also section
    deletion. This step catches and restores any backlink that was missing before
    healing or was inadvertently dropped despite preserve-first enforcement.
    ```bash
    .venv/Scripts/python scripts/pipeline/commands/ops/backlink_audit.py --family {family} --platform {platform} --subdomain {subdomain}
    ```
    If MISSING: re-inject (add-only — never rewrites or restructures existing content):
    ```bash
    .venv/Scripts/python scripts/pipeline/commands/ops/backlink_backfill.py --family {family} --platform {platform} --subdomain {subdomain} --write
    ```
    If BLOCKED_TARGET (no valid backlink target exists for this page): log WARN and
    continue. Do not fail the skill. Do not rebuild or restructure any section.

16. **Report**:
    ```
    HEAL PAGE — {file-path}
    Initial grade: {letter}

    Pass 1:
      Fixes applied: {count}
      - [{finding}]: {fix description}
      Grade after pass 1: {letter}

    Pass 2 (if needed):
      Fixes applied: {count}
      Grade after pass 2: {letter}

    RESULT: {HEALED | ESCALATED}
    Final grade: {letter}
    ```

> **Skill context close** — run after the last step:
> ```bash
> PYTHONPATH=scripts/pipeline .venv/Scripts/python scripts/pipeline/commands/governance/skill_context.py end --skill S-26 --status completed
> ```

## Post-conditions
- If HEALED: page grade is C or above, ground-check passes
- **CODE_BLOCK_BLANK_LINES**: For `products` section pages, `validate_plugin_structure.py` must exit 0 on the healed file. If `CODE_BLOCK_BLANK_LINES` errors appear in the validator output, strip blank lines at code fence boundaries and within short snippets (≤8 code lines) before accepting the heal.
- If ESCALATED: S-90 invoked for further classification; real human escalation only if S-90 confirms unresolvable per §7c
- All fixes are grounded in knowledge (no fabrication)
- Evidence frontmatter is current

## Error Handling

| Error | Cause | Fix |
|-------|-------|-----|
| `Knowledge unavailable` | Knowledge not bootstrapped | Run `/knowledge-bootstrap {family} {platform}` |
| `model.yaml stale_since` | Knowledge outdated | Run `/knowledge-update {family} {platform}` |
| Grade not improved after pass 1 | Fix didn't address root cause | Pass 2 will attempt; if still not improved → ESCALATE |
| Still D/F after 2 passes | Page has structural issues beyond auto-repair | Invoke S-90 (`/publish-readiness-review`) per §7c — S-90 classifies and routes further; real human escalation only if S-90 confirms unresolvable |
| `audit.py FAIL` persistent | Fabricated API tokens not fixable by LLM | Check api_surface.json; may need `/repo-scout` refresh |
| `no-downgrade-guard` blocked | Proposed fix would reduce grade | Examine the fix; the guard is protecting correct content |

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
