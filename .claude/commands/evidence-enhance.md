# S-83: Evidence Enhance — Improve Section Evidence Coverage on Passing Pages

**Arguments**: $ARGUMENTS
Expected format: `{relative-file-path}` — e.g.
`content/kb.aspose.org/en/email/cpp/how-to-get-started-email-cpp.md`

## Purpose

Improve section-level evidence coverage on a content page that **already passes
validation** (audit.py PASS, grade A or B). This skill is the governed entry point for
`attach_evidence.py --files --force` on passing pages.

Use when `content_eval` reports:
```
Section evidence: N/M sections covered (X%), ... [INFO]
evaluator: evidence_depth
```
and the page holds grade A or B (0 FAIL, 0–5 WARN).

**Not for**: validator failures — use S-77 (evidence-repair) for those.

## Pre-conditions

1. File exists at `$CONTENT_REPO_PATH/content/`
2. `audit.py --files {path}` exits with 0 FAIL (page already passes)
3. `knowledge/{family}/{platform}/merged/model.yaml` exists with `stale_since: null`
4. File is an English source file (refuse locale variants)

## Critical Scope Boundary

This skill ONLY modifies the `evidence:` block in YAML frontmatter. It NEVER modifies
page title, description, headings, body prose, or code blocks.

## Steps

1. **Parse arguments** from $ARGUMENTS.

2. **Pre-condition check**: Run audit to confirm page already passes:
   ```bash
   python scripts/pipeline/commands/content/audit.py --files {path}
   ```
   If any FAIL → REFUSE: "Use S-77 (evidence-repair) for failing pages."

3. **Record baseline grade**:
   ```bash
   python -m scripts.pipeline.content_eval evaluate --files {path} --format json
   ```
   Store the current grade for comparison.

4. **Run attach_evidence with --force**:
   ```bash
   python scripts/pipeline/commands/content/attach_evidence.py --files {path} --force
   ```

5. **Verify enhancement did not degrade**:
   ```bash
   python scripts/pipeline/commands/content/audit.py --files {path}
   python -m scripts.pipeline.content_eval evaluate --files {path} --format json
   ```
   - If any new FAIL → REVERT: restore original evidence block
   - If grade decreased → REVERT: restore original evidence block
   - If grade same or improved → ENHANCED

6. **Report result**:
   ```
   EVIDENCE ENHANCE — {path}
   Grade:     {before} → {after}
   Evidence sections covered: {before_pct}% → {after_pct}%
   Result: ENHANCED | REVERTED | NO_CHANGE
   ```

## Post-conditions

- ENHANCED: evidence block updated; grade same or improved; audit still passes
- REVERTED: original evidence block restored; no net change
- Page body content identical to input (no prose changes)
