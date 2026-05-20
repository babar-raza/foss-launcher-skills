<!-- Adapted from aspose.org docs/workflows/ for standalone use -->

# Evaluator Change Checklist

Run this checklist whenever you modify logic in `scripts/pipeline/content_eval/evaluators/` in a way that changes which findings are emitted, their level (FAIL/WARN), or their category. Non-grade-affecting edits (comments, docstrings, test additions, non-finding refactors) do not require a bump.

### When to bump `EVALUATOR_LOGIC_VERSION`

Bump `EVALUATOR_LOGIC_VERSION` in `scripts/pipeline/content_eval/__init__.py` if:
- A new FAIL or WARN finding is added to any evaluator
- An existing FAIL or WARN condition is changed, removed, or reclassified
- A threshold value (word count, percentage, pattern set) that gates a FAIL or WARN is changed
- A new evaluator is added to `DEFAULT_EVALUATORS`

Do NOT bump for:
- Comment or docstring changes
- Refactoring with identical output
- Adding an INFO-level finding only
- Adding a new evaluator to `ALL_EVALUATORS` but not `DEFAULT_EVALUATORS`

### How to bump

1. Increment the string in `content_eval/__init__.py`:
   ```
   EVALUATOR_LOGIC_VERSION = "2"  # was "1"
   ```
2. Re-grade all pages to stamp the new version:
   ```bash
   cd scripts/pipeline
   content_eval evaluate all --write-grade
   ```
   Pages with a different (or missing) `graded_logic_version` will be re-evaluated
   on the next `--skip-graded` run.

### What `graded_logic_version` means

`graded_logic_version` in page frontmatter records which version of the evaluator logic produced the stored grade. When `--skip-graded` is used, a page is only skipped when all four conditions are true:

| Condition | Frontmatter field checked |
|-----------|--------------------------|
| Graded with the full default evaluator set | `graded_evaluators: full` |
| Knowledge has not changed since grading | `graded_model_sha` matches current `repo_sha` |
| Evaluator logic has not changed since grading | `graded_logic_version` matches `EVALUATOR_LOGIC_VERSION` |
| Knowledge enrichment quality has not improved since grading | `graded_enrichment_status` matches current `enrichment_status` |

The `graded_enrichment_status` field records the enrichment quality at grading time (`full` or `scout-only`). If enrichment later succeeds on the same repo SHA, pages graded under `scout-only` knowledge will be re-evaluated once -- their stored grade reflects degraded knowledge and must be refreshed. After that single wave, grades persist normally. For products bootstrapped before enrichment tracking was added, the field is absent and treated as `full` (backward-compatible).

Re-grading a page that did not need it is always safe -- results are idempotent.

### Using `--skip-graded` safely

`--skip-graded` speeds up incremental runs after minor content edits. After bumping `EVALUATOR_LOGIC_VERSION`, run a full sweep **without** `--skip-graded` first so all pages are re-graded and stamped with the new version before any skipping occurs.

If enrichment quality improves for a product (e.g., a scout-only bootstrap later completes full enrichment), the next `--skip-graded` run will trigger a one-time re-evaluation wave for that product's pages. This is expected behavior -- it corrects grades produced under degraded knowledge. The wave is bounded: once pages are re-graded with `graded_enrichment_status: full`, subsequent `--skip-graded` runs skip them normally.

All skip-graded logic and grade writing is owned by `EvalRunner` (`content_eval/runner.py`). The CLI delegates to it; do not bypass the runner to write grades directly.

### Evaluator-specific triage notes

#### `encoding_check`

- **FAIL** findings indicate mojibake: UTF-8 characters that were double-encoded through a CP1252 pipeline. Source file was saved with wrong encoding or copy-pasted from a mojibake document.
- **Action**: Replace the corrupted sequences with the correct Unicode characters.
- **WARN** findings indicate stray control characters (e.g., null bytes, BEL, DEL). Likely artifact from binary paste. Delete the characters.
- Added to both `ALL_EVALUATORS` and `DEFAULT_EVALUATORS`. Scores affect grade; FAIL blocks Grade A.

#### `UNKNOWN_CLASS` WARN in `token_ops.py`

- **WARN findings with category `UNKNOWN_CLASS`** are emitted by `token_ops.py` when a code block contains `ClassName(...)` constructor syntax (or `ClassName.method(...)` dot-notation) where `ClassName` is not in `api_surface.json` and not in `PLATFORM_SDK_CLASSES`.
- **These WARN findings require triage before marking a page clean.** Classify each finding as:
  1. **FALSE-POSITIVE** (real stdlib/third-party type) -- add it to `PLATFORM_SDK_CLASSES` in `scripts/pipeline/lib/token_ops.py`. Confirm the class is a real type before executing.
  2. **TOKENIZER-ARTIFACT** (chained-call parsing error) -- suppress by adding to `PROPERTY_CHAIN_CLASSES`, or ignore if one-off.
  3. **PROBABLE-HALLUCINATION** (class not in api_surface.json, not in stdlib) -- route to heal-page to remove the hallucinated class and substitute a real API call.
- **Do not bulk-suppress** by adding classes to PLATFORM_SDK_CLASSES without verifying they are not hallucinations. Each addition must be verifiable in stdlib docs or a known third-party package.

#### `phantom_methods` -- content page coverage

- In addition to reference pages (which check filename-inferred class tables), `phantom_methods.py` now also checks content pages for explicit dot-notation method calls in markdown table cells.
- Content page checks only fire when `ClassName` is known in `api_surface.json` (prevents false positives from external classes).
- **FAIL** means a documented dot-notation method call was not found in `api_surface.json` for that class or its parents. Action: remove the phantom method or correct the class name.

#### `description_completeness` -- Grade C ceiling rule

- **Evaluator file**: `scripts/pipeline/content_eval/evaluators/description_completeness.py`
- **Rule**: Tables with >=3 data rows AND >50% empty description cells AND >=3 empty cells produce a `DC FAIL` finding.
- **Grade ceiling**: `grade_config.yaml` maps `DC: {levels: ["FAIL"], ceiling: "C"}` -- any page with a DC FAIL finding is capped at Grade C.
- **Healing strategy**: Enriching descriptions via LLM (`--mode member-doc`) populates the empty cells, which removes the DC FAIL finding. This is the correct healing path -- NOT changing evaluator thresholds.
- **Pages exempt**: Tables with <3 data rows are below the threshold and exempt.

### ELV Bump Moratorium

**`EVALUATOR_LOGIC_VERSION` bumps are suspended.** Bumping ELV rewrites frontmatter on every graded page with no content improvement. This moratorium governs all future ELV changes.

#### Allowed bump triggers (break/fix and safety only)
- A canonical evaluator produces confirmed **false results** on real pages -- fix logic and bump.
- A **safety defect**: a canonical evaluator misses genuinely dangerous content -- fix and bump.
- A one-time canonical migration when Grade Contract items are formally updated.

#### NOT allowed
- Threshold calibration (tighten/loosen FAIL/WARN sensitivity).
- Adding a new evaluator to `DEFAULT_EVALUATORS` (start it in `EXPERIMENTAL_EVALUATORS` instead).
- Improving precision or reducing false positives in an experimental evaluator.
- Any change to an evaluator in `EXPERIMENTAL_EVALUATORS` (these do not contribute to ELV).

#### Write policy -- when `--write-grade` may update frontmatter
Frontmatter grade fields are updated ONLY when:
1. Page has no grade (first grading), OR
2. Page body content changed AND the new canonical grade letter differs from the stored grade, OR
3. The grade crossed a letter boundary (A/B/C/D/F) AND human approval has been granted.

Frontmatter MUST NOT be updated when:
- Only ELV or evaluator versions changed (operational state only).
- Grade letter is unchanged even if body changed.
- A diagnostic/experimental evaluator finding changed.
- Grading was run for reporting purposes only (no healing).

#### grade_reasons must include evaluator attribution
- **Required format**: `"N FAIL finding(s) [evaluator_name x N] -> base grade X"`
- **Example**: `"1 FAIL finding(s) [api_completeness x 1] -> base grade C"`
- **NOT acceptable**: `"1 FAIL finding(s) -> base grade C"` (opaque -- no evaluator named)

#### Bulk migration annotation
Any commit touching >=20 .md files with grade-only frontmatter changes (no body changes) requires:
- Commit message: `BULK-GRADE-MIGRATION: approved by [name] on [date], reason: [policy trigger]`
- Entry in `migrations/MIGRATION_LOG.md`

### Hard-Freeze Governance Declaration

**Content may continue changing. Canonical grading behavior may not.**

The following are frozen by governance declaration:

| Frozen item | Where defined | Enforcement |
|---|---|---|
| Grade letter semantics (A-F scale) | GRADE_CONTRACT.md | Contract version bump required |
| Critical category rules (FC/PC/TA -> F) | GRADE_CONTRACT.md | Contract version bump required |
| Category ceiling structure | GRADE_CONTRACT.md | Contract version bump required |
| Canonical frontmatter schema (3 fields: grade, graded_content_hash, grade_reasons) | GRADE_CONTRACT.md, grade_writer.py | `CANONICAL_FRONTMATTER_FIELDS` frozenset |
| Frontmatter write policy semantics | GRADE_CONTRACT.md, grade_writer.py | `_should_write_canonical_grade()` gate |
| Canonical evaluator set | config.py `CANONICAL_EVALUATORS` | Contract version bump + graduation protocol |
| ELV (no bumps except break/fix) | Moratorium (above) | Guards |

What freeze does NOT prohibit: body-content edits by skills/humans, re-grading after body edits, experimental evaluator work, manifest updates, bulk operational field strip, threshold tweaks within experimental evaluators.

### Universal Skill Contract

**Applies to all skills that modify content files.**

1. **If a skill materially changes page body content, it MUST invoke the grading system in its verify/persist path.**
2. **If a skill performs analysis only (no body edit), it MAY run report-only evaluation** (no `--write-grade` flag). Report-only updates manifest only, not frontmatter.
3. **A skill MUST NOT write canonical frontmatter for operational-only changes.** If only metadata changed but body did not change, no frontmatter write is permitted.
4. **A skill MUST respect canonical/experimental separation.** Experimental evaluator findings MUST NOT appear in `grade_reasons` or affect the canonical grade letter.
5. **A skill MUST NOT change canonical grading behavior** (evaluator code, canonical evaluator set, grade semantics, write policy logic, ELV) **unless the Emergency Grading-Change Protocol (below) is invoked.**

### Emergency Grading-Change Protocol

**When this protocol applies:**
- A canonical evaluator produces confirmed false results (wrong FAIL or wrong PASS) on real pages
- A safety defect: a canonical evaluator misses genuinely dangerous content
- A critical category rule is provably wrong

**When this protocol does NOT apply:** precision improvements to experimental evaluators, threshold tweaks within experimental evaluators, adding new experimental evaluators, content body edits by skills or humans.

**Steps:**
1. Document the defect -- cite specific affected pages, classify as safety (same-day) or accuracy (48h).
2. Obtain human approval -- owner must explicitly approve. No agent may proceed without approval.
3. Fix the evaluator -- minimum necessary change; do not bundle unrelated improvements.
4. Bump ELV -- update `EVALUATOR_LOGIC_VERSION` in `__init__.py` AND update `EVALUATOR_FREEZE_VERSION` to match.
5. Create MIGRATION_LOG.md entry -- document what changed, why, which pages affected, approval reference.
6. Re-evaluate affected pages only -- run content_eval evaluate on specific pages only.
7. Invalidate prior readiness verdicts if bulk migration has not yet executed.
8. Update GRADE_CONTRACT.md if frozen items changed -- bump contract version.

**Key constraint:** Break/fix only. Not a backdoor for calibration or precision improvements.
