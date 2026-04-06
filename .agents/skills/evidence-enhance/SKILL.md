---
name: evidence-enhance
description: >
  <!-- CONTRACT: scripts/pipeline/attach_evidence.py --files {path} --force (thin wrapper)
---

> Cross-skill references like `/knowledge-bootstrap` refer to sibling skills in this directory.

# S-78: Evidence Enhance — Improve Section Evidence Coverage on Passing Pages

<!-- CONTRACT: scripts/pipeline/attach_evidence.py --files {path} --force (thin wrapper)
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
   python scripts/pipeline/audit.py --files {path}
   ```
   If audit returns any FAIL, HALT:
   ```
   REFUSED: Page has audit failures. Use S-72 (evidence-repair) for validator-blocked pages.
   ```
8. Check current evidence coverage:
   ```bash
   python -m scripts.pipeline.content_eval evaluate --files {path} --format json
   ```
   If `evidence_depth` INFO finding is absent (coverage already 100%), report NO_CHANGE
   and exit without modifying the file.

## Steps

1. **Capture baseline**: Record current `evidence_depth` finding (section count, API count,
   claim count) from the pre-flight eval output.

2. **Auto-refresh knowledge**:
   ```bash
   python scripts/pipeline/refresh_knowledge.py {family} {platform}
   ```

3. **Run attach_evidence**:
   ```bash
   python scripts/pipeline/attach_evidence.py --files {path} --force
   ```

4. **Post-attach audit**:
   ```bash
   python scripts/pipeline/audit.py --files {path}
   ```
   If audit returns any FAIL, revert the file to its pre-step-3 state and report ESCAPED:
   ```
   ESCAPED: attach_evidence.py introduced an audit violation. File reverted.
   ```

5. **Validate frontmatter**:
   ```bash
   python scripts/pipeline/validate_frontmatter.py --files {path}
   ```
   If validation fails, revert and report ESCAPED.

6. **Update provenance**:
   Set `provenance.last_mechanism: evidence-enhance` in the frontmatter.

7. **Re-evaluate**:
   ```bash
   python -m scripts.pipeline.content_eval evaluate --files {path} --format json
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

## Post-conditions

- `audit.py` exits 0
- `validate_frontmatter.py` exits 0
- Grade is unchanged or improved
- WARN count is unchanged or reduced (must not increase)
- `provenance.last_mechanism` is `evidence-enhance`
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
