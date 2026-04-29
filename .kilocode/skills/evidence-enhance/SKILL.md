---
name: evidence-enhance
description: >
  <!-- CONTRACT: scripts/pipeline/commands/healing/attach_evidence.py --files {path} --force (thin wrapper)
---

> Cross-skill references like `/knowledge-bootstrap` refer to sibling skills in this directory.

# S-78: Evidence Enhance — Improve Section Evidence Coverage on Passing Pages

<!-- CONTRACT: scripts/pipeline/commands/healing/attach_evidence.py --files {path} --force (thin wrapper)
postcondition: page must pass audit.py BEFORE and AFTER the skill runs
postcondition: skill is evidence-frontmatter-only — page body content is NEVER modified
postcondition: validate_frontmatter.py + audit.py both exit 0 before reporting ENHANCED
postcondition: grade must not decrease after evidence update
verified: 2026-04-06
-->

**Arguments**: $ARGUMENTS
Expected format: `{relative-file-path}` — e.g.
`content/kb.aspose.org/en/email/cpp/how-to-get-started-email-cpp.md`

## Purpose

Improve section-level evidence coverage on a content page that **already passes
validation** (audit.py PASS, grade A or B). This skill is the governed entry point for
`attach_evidence.py --files --force` on passing pages.

This skill is triggered when `content_eval` reports:

```
Section evidence: N/M sections covered (X%), ... [INFO]
evaluator: evidence_depth
```

and the page holds grade A or B (0 FAIL, 0–5 WARN). It is **not** triggered by validator
failures — use **S-72 (evidence-repair)** for those.

**Critical scope boundary**: This skill ONLY modifies the `evidence:` and `provenance:`
blocks in the YAML frontmatter. It NEVER modifies page title, description, body content,
headings, code blocks, or any prose text.

**Relationship to S-72**: S-72 handles validator-blocked pages (P-03, audit FAIL). S-78
handles passing pages with incomplete section evidence. Their pre-conditions are mutually
exclusive: S-78 requires audit.py PASS; S-72 handles audit.py FAIL.

## Pre-conditions (Preflight — halt immediately on any failure)

1. Parse file path from `$ARGUMENTS`.
2. File must exist under an allowed `content/` path.
3. File must be an English source file — refuse locale variants (`index.ar.md`, etc.).
4. Detect `{family}` and `{platform}` from the file path.
5. `knowledge/{family}/{platform}/merged/model.yaml` must exist and have `stale_since: null`.
   If stale, HALT:
   ```
   REFUSED: Knowledge is stale for {family}/{platform}.
   Run S-12 (knowledge-diff) then S-14 (knowledge-update) before proceeding.
   ```
6. `knowledge/{family}/{platform}/merged/claims.json` and `api_surface.json` must exist.
7. **Pre-flight audit** — the page must already be clean:
   ```bash
   .venv/Scripts/python scripts/pipeline/commands/content/audit.py --files {path}
   ```
   If audit returns any FAIL, HALT:
   ```
   REFUSED: Page has audit failures. Use S-72 (evidence-repair) for validator-blocked pages.
   ```
8. Check current evidence coverage:
   ```bash
   .venv/Scripts/python -m scripts.pipeline.content_eval evaluate --files {path} --format json
   ```
   If `evidence_depth` INFO finding is absent (coverage already 100%), report NO_CHANGE
   and exit without modifying the file.

## Step 0b — Preflight Classification

Run a static classification of the page **before any script execution**. This step is
read-only and deterministic. HALT immediately on `SKIPPED-DEGRADE-RISK` or `UNCERTAIN`.

1. Read `evidence.apis` from the frontmatter.
   - If non-empty, the page has manually-set API evidence.
2. Extract API token candidates from the page's fenced code blocks using
   `token_ops.extract_tokens(path, platform)` — the same tokenizer as `attach_evidence.py`.
   - Exclude import tokens and constructor tokens (`member_name == "__init__"`).
3. Check token coverage against the in-memory `Knowledge.api_to_claim` index (built from
   `knowledge/{family}/{platform}/merged/claims.json`).
   - `covered` = tokens whose `ClassName.method` key appears in `api_to_claim`
   - `uncovered` = tokens not in `api_to_claim`

**Classification table** (evaluated in order):

| `evidence.apis` | `covered` tokens | Outcome |
|-----------------|-----------------|---------|
| non-empty | 0 | `SKIPPED-DEGRADE-RISK` |
| non-empty | > 0, fewer than `len(existing_apis)` | `SKIPPED-DEGRADE-RISK` |
| non-empty | ≥ `len(existing_apis)` | `no-op` → proceed to Step 8 (report NO_CHANGE) |
| empty | > 0 | `viable` → continue to Step 1 |
| empty | 0, but code blocks exist | `UNCERTAIN` → escalate to operator |
| empty | no code blocks at all | `no-op` → proceed to Step 8 (report NO_CHANGE) |

**On `SKIPPED-DEGRADE-RISK`** — halt and report without running any script:
```
CLASSIFICATION: SKIPPED-DEGRADE-RISK
Reason: Page has {N} manually-set APIs; auto-detect would produce {M} APIs (covered tokens).
Running attach_evidence.py would overwrite the manual evidence panel with a shorter list.
Action: No script executed. File unchanged.
```

**On `UNCERTAIN`** — halt and escalate:
```
CLASSIFICATION: UNCERTAIN
Reason: Page has {N} code block(s) but 0 API tokens match the api_to_claim index.
This may indicate incomplete index coverage or non-standard API naming.
Action: Escalate to operator. Do not run script without explicit authorization.
```

**Note on tokenizer scope**: `extract_tokens` only extracts constructors, static method
calls, and instance method calls where the variable type can be inferred from a prior typed
assignment in the same code block. Regex scanning of method names in prose or table cells
will produce false `viable` classifications — always use the tokenizer, not regex.

## Steps

> **Skill context gate** — run before step 1:
> ```bash
> PYTHONPATH=scripts/pipeline .venv/Scripts/python scripts/pipeline/commands/governance/skill_context.py begin --skill S-78 --scope "*"
> ```


1. **Capture baseline**: Record current `evidence_depth` finding (section count, API count,
   claim count) from the pre-flight eval output.

2. **Auto-refresh knowledge**:
   ```bash
   .venv/Scripts/python scripts/pipeline/commands/knowledge/refresh_knowledge.py {family} {platform}
   ```

3. **Run attach_evidence**:
   ```bash
   .venv/Scripts/python scripts/pipeline/commands/healing/attach_evidence.py --files {path} --force
   ```

4. **Post-attach audit**:
   ```bash
   .venv/Scripts/python scripts/pipeline/commands/content/audit.py --files {path}
   ```
   If audit returns any FAIL, revert the file to its pre-step-3 state and report ESCAPED:
   ```
   ESCAPED: attach_evidence.py introduced an audit violation. File reverted.
   ```

5. **Validate frontmatter**:
   ```bash
   .venv/Scripts/python scripts/pipeline/commands/content/validate_frontmatter.py --files {path}
   ```
   If validation fails, revert and report ESCAPED.

6. **Provenance**: Do NOT update `provenance.last_mechanism`. Per `provenance.py` lifecycle
   rules (lines 51–55), evidence attachment is not a content-changing operation and must
   not call `update_mechanism()` or change `last_mechanism`. The existing value is preserved.

7. **Re-evaluate**:
   ```bash
   .venv/Scripts/python -m scripts.pipeline.content_eval evaluate --files {path} --format json
   ```
   Record new `evidence_depth` finding. If WARN count has increased or grade has decreased,
   revert the file and report ESCAPED.

8. **Report**:
   ```
   EVIDENCE ENHANCE — {file-path}

   Before: {N}/{M} sections covered ({X}%), {A} APIs, {C} claims  [WARN count: W]
   After:  {N'}/{M} sections covered ({X'}%), {A'} APIs, {C'} claims [WARN count: W']

   Result: ENHANCED | NO_CHANGE | ESCAPED
   Grade:  {before} → {after} (must not decrease)
   ```

> **Skill context close** — run after the last step:
> ```bash
> PYTHONPATH=scripts/pipeline .venv/Scripts/python scripts/pipeline/commands/governance/skill_context.py end --skill S-78 --status completed
> ```

## Post-conditions

- `audit.py` exits 0
- `validate_frontmatter.py` exits 0
- Grade is unchanged or improved
- WARN count is unchanged or reduced (must not increase)
- `provenance.last_mechanism` is **unchanged** — evidence-only operations must not change it (lifecycle rule in `provenance.py:51–55`)
- Page body content is byte-for-byte identical to pre-skill state

## Known Limitations

**attach_evidence.py merge behavior**: The script merges `claims` (preserves manually set
claim IDs) but does **not** preserve manually set `apis`, `formats`, or section-level
evidence entries. If `--force` produces empty `apis` where manual entries existed, the
resulting state will have more WARNs than before (the evaluator will flag "API-eligible
code blocks but 0 evidence APIs"). The skill detects this via WARN count check in Step 7
and reverts (ESCAPED). For pages with rich manually set evidence panels, S-78 is not
applicable — evidence already exceeds what the script can auto-detect.

**When S-78 produces ESCAPED on a manually-evidenced page**: This is not a skill failure.
It means the page's evidence is already at or above auto-detection quality. No further
action is needed. File the ESCAPED result and close the track.

## Never Do

- Modify page title, body, headings, code blocks, or prose
- Invent claim IDs not present in `claims.json`
- Invent API refs not present in `api_surface.json`
- Run on a page with audit failures (S-72 handles those)
- Run on locale translation files (`index.ar.md`, etc.)
- Proceed when knowledge is stale
- Skip the pre-flight audit check
- Skip the post-attach audit check
- Accept a grade decrease as an acceptable outcome

## Error Handling

| Condition | Action |
|-----------|--------|
| Pre-flight audit FAIL | HALT with REFUSED; redirect to S-72 |
| Knowledge stale | HALT with REFUSED; redirect to S-14 |
| Post-attach audit FAIL | Revert file; report ESCAPED |
| Frontmatter validation FAIL after attach | Revert file; report ESCAPED |
| Grade decreases after attach | Revert file; report ESCAPED |
| WARN count increases after attach | Revert file; report ESCAPED — attach_evidence.py may have cleared manually set apis or formats that were richer than auto-detected evidence; manual evidence takes precedence |
| Coverage already 100% | Report NO_CHANGE; no file writes |
| attach_evidence.py not found | HALT with REFUSED; check pipeline installation |
