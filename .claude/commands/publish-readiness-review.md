<!-- CONTRACT: agent-executed
     purpose: agent-executed governed inspection — replace "human-review" dead-ends with
              bounded inspection, judgment, skill routing, re-verification, and verdict
     preconditions: knowledge model current; content_eval grades current at EVALUATOR_LOGIC_VERSION
     postcondition: per-page publish disposition recorded; fix skills invoked for actionable items;
                    final-verdict.md written with PUBLISH | CONDITIONAL | BLOCKED recommendation
     idempotent: no — LLM-based fix skills vary; --dry-run flag enables safe re-inspection
     verified: 2026-04-17
     depends_on: [S-54, S-25]
-->
# S-90: Publish Readiness Review — Agent-Executed Governed Inspection

**Arguments**: $ARGUMENTS
Expected format: `{family} {platform} [--scope all|non-reference|reference|blog|kb|docs|products] [--from-verdict {path}] [--grade-filter A,B,C,D,F] [--triage-unknowns] [--dry-run]`

## Purpose

Perform bounded manual-style inspection of content pages, make judgment calls against
knowledge artifacts, route actionable pages to appropriate fix skills (S-21, S-26,
/batch-reference, S-65, S-38), re-evaluate after fixes, and emit an evidence-backed
publish verdict.

**This skill is the governed replacement for all "human-review" dead-ends** in the
system. When any skill, plan, or report says "escalate to human review", "manual
review required", "human action required", or equivalent, agents MUST invoke this
skill rather than halting — see AGENTS.md §7c for the canonical definition.
(Launch gates: [docs/governance/launch-gates.md](../docs/governance/launch-gates.md))

**When real human escalation is still required** (S-90 routes these, does not execute):
- Grade F after 2 S-26 passes + 1 S-89 batch pass with no improvement
- PIPELINE-bucket findings from S-87 (skill breakage, extraction failure)
- `tier3_non_determinism_flag: true` findings (evaluator non-determinism)
- Legal, license, or business claims requiring external verification

## Pre-conditions

1. `{family}` and `{platform}` arguments parsed
2. Knowledge model current: `knowledge/{family}/{platform}/merged/model.yaml` has `stale_since: null`
   — if stale, run `/knowledge-update {family} {platform}` first
3. Content pages have been graded at current `EVALUATOR_LOGIC_VERSION`:
   — check `graded_logic_version` in page frontmatter matches `EVALUATOR_LOGIC_VERSION` from
     `scripts/pipeline/content_eval/__init__.py`; if stale, re-run `content_eval evaluate`
4. If `--from-verdict {path}` is supplied, that file must exist

## Arguments

| Argument | Default | Description |
|----------|---------|-------------|
| `--scope` | `all` | Limit to page type: `all`, `non-reference`, `reference`, `blog`, `kb`, `docs`, `products` |
| `--from-verdict {path}` | none | Path to audit verdict for context (e.g. `reports/audit/final-verdict-2026-04-17.md`) |
| `--grade-filter A,B,C,D,F` | all | Only inspect pages at these grade levels |
| `--triage-unknowns` | off | Also classify UNKNOWN_CLASS WARN findings in code blocks |
| `--dry-run` | off | Inspect and classify only; do not invoke fix skills |

## Steps

> **Skill context gate** — run before step 1:
> ```bash
> PYTHONPATH=scripts/pipeline .venv/Scripts/python scripts/pipeline/commands/governance/skill_context.py begin --skill S-90 --scope "{family}/{platform}"
> ```

1. **Parse arguments**: Extract `{family}`, `{platform}`, `{scope}`, and flags from $ARGUMENTS.

2. **Auto-refresh knowledge**: Ensure knowledge artifacts are current.
   ```bash
   .venv/Scripts/python scripts/pipeline/commands/knowledge/refresh_knowledge.py {family} {platform}
   ```
   If it prints "refreshed", knowledge was stale and has been rebuilt. If it prints "current",
   proceed. If clone cache is missing, warn and continue with existing artifacts.

3. **Load knowledge artifacts**:
   - Read `knowledge/{family}/{platform}/merged/api_surface.json` — class/method truth
   - Read `knowledge/{family}/{platform}/merged/formats.json` — format support truth
   - Read `knowledge/{family}/{platform}/merged/claims.json` — semantic claims
   - Read `knowledge/{family}/{platform}/merged/limitations.md` — known unimplemented features
   - If `--from-verdict` supplied: read that file for context on known gaps and prior actions

4. **Build page roster**: Enumerate all content pages in scope.

   ```bash
   # Non-reference:
   find content/docs.aspose.org/en/{family}/{platform}/ -name "*.md"
   find content/blog.aspose.org/{family}/{platform}/ -name "*.md"
   find content/kb.aspose.org/en/{family}/{platform}/ -name "*.md"
   find content/products.aspose.org/en/{family}/ -name "*.md"
   # Reference:
   find content/reference.aspose.org/en/{family}/{platform}/ -name "*.md"
   ```

   Apply `--scope` filter. Apply `--grade-filter` by reading `graded_at` + `graded_grade` from
   page frontmatter. Apply `draft: true` exclusion (skip draft pages).

5. **Inspect each page** — for each page in the roster, perform bounded inspection:

   **5a. Read current grade and findings**:
   - Read `graded_grade`, `graded_at`, `graded_fail_count`, `graded_warn_count` from frontmatter
   - If grade is stale (logic version mismatch): re-evaluate inline:
     ```bash
     .venv/Scripts/python -m scripts.pipeline.content_eval evaluate --files {page-path} --format json
     ```

   **5b. Read page content** (title, section headers, code blocks, format tables).
   > **MANUAL GATE (H-01 prose review)**: No automated prose-hallucination evaluator
   > exists. Prose accuracy is a judgment call by the inspecting agent: check that
   > factual claims in the prose are consistent with `claims.json` and that no
   > non-existent API classes appear in prose descriptions. Future: `prose_accuracy_check.py`.

   **5c. Classify each page** using this decision table:

   | Condition | Classification |
   |-----------|---------------|
   | Grade A or B, 0 FAIL | PUBLISH-READY |
   | Grade B, WARNs only (no FAIL) | PUBLISH-READY |
   | Grade C, non-reference page | NEEDS-ACTION (route S-21) |
   | Grade C, reference page with `evidence.apis` non-empty | ACCEPTABLE-GRADE-C (publish-eligible per §6) |
   | Grade C, reference page with `evidence.apis` empty | STRUCTURAL-GAP (route /batch-reference) |
   | Grade D | NEEDS-ACTION (route S-26) |
   | Grade F, reference page with prose < 20 words | STRUCTURAL-GAP (route /batch-reference) |
   | Grade F, non-reference page | BLOCKED (route S-26, 2 passes; if still F → escalate) |
   | `draft: true` already set | SKIP |

   **5d. Check code blocks against `api_surface.json`** (sample check for PUBLISH-READY pages):
   - For pages classified as PUBLISH-READY: scan code blocks for constructor calls `ClassName(...)`.
   - If `ClassName` not in `api_surface.json` and not in Python stdlib: downgrade to NEEDS-ACTION;
     add note "UNKNOWN_CLASS: {ClassName}".

   **5e. Check format claims against `formats.json`** (for pages with format tables):
   - Find any markdown table with Import/Export or Read/Write columns.
   - For each format row, verify claimed support matches `formats.json`. If mismatch: downgrade
     to NEEDS-ACTION; add note "FORMAT_MISMATCH: {format} claimed {direction} but formats.json
     shows {actual}".

   **5f. UNKNOWN_CLASS triage** (when `--triage-unknowns` flag is set):
   - For each WARN finding with category `UNKNOWN_CLASS`:
     - Extract class name from WARN context.
     - Check Python stdlib list: `builtins`, `io`, `datetime`, `pathlib`, `os`, `typing`, `collections`.
       If match → classify as FALSE-POSITIVE.
     - Check `api_surface.json` for the class name under any known class's methods/properties.
       If match → classify as TOKENIZER-ARTIFACT.
     - If neither → classify as PROBABLE-HALLUCINATION; add to NEEDS-ACTION list.
   - Record classification for each WARN in `triage-unknowns.json`.

6. **Write inspection manifest**:
   Create `reports/publish-review/{family}-{platform}-{YYYYMMDD}/inspection-manifest.json`:
   ```json
   {
     "family": "{family}",
     "platform": "{platform}",
     "scope": "{scope}",
     "inspected_at": "{ISO timestamp}",
     "evaluator_logic_version": "{version}",
     "pages": [
       {
         "path": "{relative-path}",
         "grade": "{A|B|C|D|F}",
         "fail_count": N,
         "warn_count": N,
         "classification": "PUBLISH-READY|NEEDS-ACTION|ACCEPTABLE-GRADE-C|STRUCTURAL-GAP|BLOCKED|SKIP",
         "classification_reason": "{why}",
         "action": "none|S-21|S-26|batch-reference|S-26+escalate|skip",
         "notes": ["{note1}", ...]
       }
     ],
     "summary": {
       "publish_ready": N,
       "needs_action": N,
       "acceptable_grade_c": N,
       "structural_gaps": N,
       "blocked": N,
       "skipped": N
     }
   }
   ```

   If `--dry-run`: output this manifest and stop; do not proceed to Step 7.

7. **Route to fix skills** (skip if `--dry-run`):

   **7a. NEEDS-ACTION, Grade C → S-21 (page-enhance)**:
   For each page classified as NEEDS-ACTION with grade C:
   - Invoke S-21 per its contract: read page, enhance against knowledge, re-evaluate.
   - Record result in `action-log.json`: skill invoked, pre-grade, post-grade, outcome.

   **7b. NEEDS-ACTION, Grade D → S-26 (heal-page)**:
   For each page classified as NEEDS-ACTION with grade D:
   - Invoke S-26 per its contract (up to 2 passes).
   - Record result in `action-log.json`.

   **7c. BLOCKED, Grade F non-stub → S-26 (2 passes)**:
   For each page classified as BLOCKED with grade F (non-stub):
   - Invoke S-26 (up to 2 passes).
   - If grade improves to C or above: reclassify as NEEDS-ACTION, potentially route to S-21.
   - If still F after 2 passes: classify as ESCALATED with reason "grade-F-unresolved".

   **7d. STRUCTURAL-GAP → /batch-reference**:
   For reference pages classified as STRUCTURAL-GAP:
   - Group by product (family/platform).
   - Queue `/batch-reference {family} {platform}` invocation.
   - Note: batch-reference is idempotent; existing pages are never overwritten.
   - After batch-reference completes: re-evaluate queued pages.

   **7e. Dead links → S-65 + S-74**:
   If the `--from-verdict` file mentions dead internal links, or if any FAIL findings
   relate to broken links:
   - Invoke S-65 (link-validate) for the product.
   - If broken links found: invoke S-74 (causal-backtrack) per its protocol.

   **7f. Format mismatches → content_eval + S-73**:
   For pages with FORMAT_MISMATCH notes:
   - Run targeted format_truth evaluation:
     ```bash
     .venv/Scripts/python -m scripts.pipeline.content_eval evaluate --files {page-path} \
       --evaluators format_truth --format json
     ```
   - If FAIL confirmed: invoke S-73 (manual-edit) with `--scope body-wording` to correct
     the format table.

   **7g. H-02 reference accuracy** (equivalent to launch gate H-02):
   For a stratified sample of reference pages classified as ACCEPTABLE-GRADE-C:
   - Select up to 10 pages with the highest `evidence.apis` coverage.
   - For each: check that every listed class in `evidence.apis` exists in `api_surface.json`.
   - If a class is absent: downgrade to STRUCTURAL-GAP; add to S-38 (truth-audit) queue.
   - Invoke S-38 on the queue if non-empty.

   **7g2. Backlink compliance gate** (TC-BL-003):
   ```bash
   .venv/Scripts/python scripts/pipeline/commands/ops/backlink_audit.py \n     --family {family} --platform {platform}
   ```
   For any MISSING pages: remediate before marking READY TO SHIP:
   ```bash
   .venv/Scripts/python scripts/pipeline/commands/ops/backlink_backfill.py \n     --family {family} --platform {platform} --write
   ```
   If BLOCKED_TARGET: record in readiness report — do not block READY TO SHIP on
   BLOCKED_TARGET alone (target site controls the link, not this repo).

   **7h. H-05 license accuracy**:
   - Read `LICENSE` file from clone cache at
     `runs/.clone_cache/aspose_{family}_{platform}/LICENSE`
   - Read license claim from products page frontmatter or prose.
   - If mismatch: record as ESCALATED with reason "license-mismatch" (real human required).

8. **Re-evaluate all actioned pages**:
   For every page that was actioned in Step 7 (S-21, S-26, batch-reference):
   ```bash
   .venv/Scripts/python -m scripts.pipeline.content_eval evaluate --files {actioned-pages} \
     --write-grade --format json
   ```
   Compare pre-action vs. post-action grades. Record in `re-evaluation-results.json`.

9. **Write action log**:
   Create `reports/publish-review/{family}-{platform}-{YYYYMMDD}/action-log.json`:
   ```json
   {
     "actions": [
       {
         "page": "{path}",
         "skill_invoked": "S-21|S-26|batch-reference|S-65|S-38|S-73",
         "pre_grade": "{letter}",
         "post_grade": "{letter}",
         "outcome": "improved|unchanged|reclassified|escalated",
         "escalation_reason": "{reason if escalated or null}"
       }
     ]
   }
   ```

10. **Write triage-unknowns log** (if `--triage-unknowns` was set):
    Create `reports/publish-review/{family}-{platform}-{YYYYMMDD}/triage-unknowns.json`:
    ```json
    {
      "unknowns": [
        {
          "page": "{path}",
          "class_name": "{ClassName}",
          "context": "{surrounding code snippet}",
          "classification": "FALSE-POSITIVE|TOKENIZER-ARTIFACT|PROBABLE-HALLUCINATION",
          "action": "add-to-platform-sdk-classes|suppress|route-to-S26"
        }
      ]
    }
    ```
    For FALSE-POSITIVE entries: prepare an S-73 invocation to add the class name to
    `PLATFORM_SDK_CLASSES` in `scripts/pipeline/lib/token_ops.py`.
    **Note**: Additions to `PLATFORM_SDK_CLASSES` require the operator to verify the class
    is a real stdlib/third-party type before executing the S-73 invocation.

11. **Write final verdict**:
    Create `reports/publish-review/{family}-{platform}-{YYYYMMDD}/final-verdict.md`:

    ```markdown
    # Publish Readiness Verdict — {family}/{platform}
    **Date**: {YYYY-MM-DD}
    **Scope**: {scope}
    **Evaluator logic version**: {version}
    **Post-action re-grade**: yes/no (--dry-run was used: yes/no)

    ## Section Verdicts

    | Section | Verdict | Pages | Notes |
    |---------|---------|-------|-------|
    | blog | READY / CONDITIONAL / BLOCKED | N pages | {reason if not READY} |
    | docs | READY / CONDITIONAL / BLOCKED | N pages | |
    | kb | READY / CONDITIONAL / BLOCKED | N pages | |
    | products | READY / CONDITIONAL / BLOCKED | N pages | |
    | reference (grade A/B) | READY | N pages | |
    | reference (acceptable grade C) | READY (grade-C floor per §6) | N pages | |
    | reference (structural gaps) | BLOCKED | N pages | Run /batch-reference to unblock |

    ## Actions Taken

    - {N} pages enhanced via S-21 (page-enhance)
    - {N} pages healed via S-26 (heal-page)
    - {N} reference stubs queued for /batch-reference
    - {N} dead links resolved via S-65 + S-74
    - {N} UNKNOWN_CLASS WARNs triaged ({breakdown: false-positive/artifact/hallucination})

    ## Still Blocked

    | Page | Reason | Required action |
    |------|--------|-----------------|
    | {path} | grade-F-unresolved | Real human escalation per §7c condition 1 |
    | {path} | license-mismatch | Real human verification per §7c condition 4 |

    ## Escalated to Human

    {List only items matching real-escalation conditions from §7c.
     If empty: write "None — all reviewable items handled by governed inspection."}

    ## Final Recommendation

    **PUBLISH** / **CONDITIONAL** / **BLOCKED**

    {Rationale: what was done, what changed, what remains, and why the recommendation follows.}
    ```

12. **Report to operator**:
    ```
    PUBLISH READINESS REVIEW — {family}/{platform}
    Scope: {scope} | Pages inspected: {N} | Post-action re-grade: yes/no

    CLASSIFICATIONS:
      Publish-ready:        {N}
      Needs-action (done):  {N} (S-21: {N}, S-26: {N})
      Acceptable grade-C:   {N} (reference stubs — publish-eligible per §6)
      Structural gaps:      {N} (batch-reference queued/run)
      Blocked:              {N} (see final-verdict.md)
      Escalated to human:   {N} (see final-verdict.md)

    GRADE IMPROVEMENT:
      Pre-action:  A:{N} B:{N} C:{N} D:{N} F:{N}
      Post-action: A:{N} B:{N} C:{N} D:{N} F:{N}

    VERDICT: {PUBLISH | CONDITIONAL (actions taken, {N} remain) | BLOCKED}
    Full report: reports/publish-review/{family}-{platform}-{YYYYMMDD}/final-verdict.md
    ```

> **Skill context close** — run after the last step:
> ```bash
> PYTHONPATH=scripts/pipeline .venv/Scripts/python scripts/pipeline/commands/governance/skill_context.py end --skill S-90 --status completed
> ```

## Post-conditions

- `reports/publish-review/{family}-{platform}-{YYYYMMDD}/` exists with all output files
- `inspection-manifest.json` has a classification for every page in scope
- `action-log.json` has an entry for every actioned page
- `final-verdict.md` has per-section READY/CONDITIONAL/BLOCKED with rationale
- All actioned pages have been re-evaluated and grades updated
- Escalated items have concrete escalation reasons (not vague "needs human")

## Error Handling

| Error | Cause | Fix |
|-------|-------|-----|
| `Knowledge unavailable` | Knowledge not bootstrapped | Run `/knowledge-bootstrap {family} {platform}` |
| `model.yaml stale_since` | Knowledge outdated | Run `/knowledge-update {family} {platform}` |
| `graded_logic_version` mismatch | Grades from older evaluator | Re-run `content_eval evaluate --write-grade` first |
| S-21 invocation fails | Page-enhance precondition not met | Check eval-page grade; invoke S-25 first |
| S-26 invocation fails | Heal-page precondition not met | Check knowledge freshness; run S-14 if stale |
| `/batch-reference` skips all pages | Pages already exist | Idempotent by design; stubs need enrichment via `enrich.py --mode member-doc` first |
| Clone cache missing (H-05) | License check cannot run | Record as DEFERRED; operator runs `/repo-scout` to restore cache |

## Composition (skills invoked internally)

| Skill | When invoked |
|-------|-------------|
| S-14 (knowledge-update) | Step 2, if knowledge is stale |
| S-21 (page-enhance) | Step 7a, for grade C NEEDS-ACTION pages |
| S-26 (heal-page) | Step 7b/7c, for grade D or F pages |
| S-38 (truth-audit) | Step 7g, H-02 reference accuracy check |
| S-65 (link-validate) | Step 7e, for dead link findings |
| S-73 (manual-edit) | Step 7f/7j, for format corrections and UNKNOWN_CLASS fixes |
| S-74 (causal-backtrack) | Step 7e, for broken-link upstream resolution |
| /batch-reference (S-62) | Step 7d, for STRUCTURAL-GAP reference pages |

## Enterprise Backlink Policy

All enterprise links generated or modified by this skill must comply with
[docs/governance/backlink-policy.md](../docs/governance/backlink-policy.md):
- Links must originate exclusively from `backlink_authority.json` (Layer 3)
- No manual URL construction or interpolation permitted
- Anchor text sourced from `anchor_text_registry.yaml` only
- Cross-section fallback to `products.aspose.com` is prohibited for non-products sources
