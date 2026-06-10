# S-95: Publish Readiness Review — Agent-Executed Governed Inspection

**Arguments**: $ARGUMENTS
Expected format: `{family} {platform} [--scope all|non-reference|reference|blog|kb|docs|products] [--from-verdict {path}] [--grade-filter A,B,C,D,F] [--triage-unknowns] [--dry-run]`

## Purpose

Perform bounded manual-style inspection of content pages, make judgment calls against
knowledge artifacts, route actionable pages to appropriate fix skills, re-evaluate after
fixes, and emit an evidence-backed publish verdict.

**This skill is the governed replacement for all "human-review" dead-ends** in the system.
When any skill, plan, or report says "escalate to human review", "manual review required",
or equivalent, agents MUST invoke this skill instead of halting.

## Pre-conditions

1. `knowledge/{family}/{platform}/merged/model.yaml` with `stale_since: null`
2. Content pages exist for the target scope
3. `content_eval` grades are current

## Verdict Levels

| Verdict | Meaning |
|---|---|
| `PUBLISH` | All in-scope pages pass; no blocking issues |
| `CONDITIONAL` | Minor issues remain; acceptable for publish with documented caveats |
| `BLOCKED` | Critical issues present; must be resolved before publish |

## Steps

1. **Parse arguments** and determine scope.

2. **Load existing eval grades** (or run content_eval if not current):
   ```bash
   python -m scripts.pipeline.content_eval evaluate \
     --family {family} --platform {platform} --scope {scope} --format json
   ```

3. **Apply grade filter**: If `--grade-filter` provided (e.g. `C,D,F`), focus inspection
   on pages at those grades. Skip grade A/B pages from detailed inspection.

4. **Inspect each flagged page**:
   For each page requiring inspection:
   a. Read the full page content
   b. Read the relevant `claims.json` entries
   c. Make a judgment call: is this finding actionable, a false positive, or acceptable?
   d. Classify: `ACTIONABLE`, `FALSE_POSITIVE`, `ACCEPTABLE_RISK`, `BLOCKED`

5. **Route actionable pages** to fix skills:
   - Grade C (minor issues) → S-21 (page-enhance)
   - Grade D/F (significant issues) → S-26 (heal-page)
   - Broken cross-site links → S-70 (link-validate)
   - Missing API accuracy → S-47 (truth-audit)
   - Structural issues → S-78 (manual-edit)

6. **Re-evaluate after fixes**:
   ```bash
   python -m scripts.pipeline.content_eval evaluate --files {fixed-pages} --format json
   ```

7. **Triage UNKNOWN pages** (if `--triage-unknowns`): Pages without a current grade are
   inspected and classified. Unclassified pages default to `CONDITIONAL`.

8. **Write final verdict** to `reports/publish-readiness/{family}-{platform}-{date}.md`:
   ```markdown
   # Publish Readiness: {Family} {Platform}
   **Date**: {ISO date}
   **Verdict**: PUBLISH | CONDITIONAL | BLOCKED

   ## Summary
   Pages inspected: N
   PUBLISH (grade A/B): N
   CONDITIONAL (grade C): N
   BLOCKED (grade D/F): N

   ## Blocking Issues
   (for BLOCKED verdict only)

   ## Caveats
   (for CONDITIONAL verdict)

   ## Sign-off
   Skill: S-95 | Run: {timestamp}
   ```

9. **Print verdict**:
   ```
   PUBLISH READINESS REVIEW — {family}/{platform}
   Scope: {scope}
   Verdict: PUBLISH | CONDITIONAL | BLOCKED

   Blocking issues: N
   Caveats: N
   Report: reports/publish-readiness/{family}-{platform}-{date}.md
   ```

## Post-conditions

- Final verdict written to `reports/publish-readiness/`
- All ACTIONABLE issues either fixed or documented as caveats
- No "escalate to human" dead-ends — all decisions made within this skill

## Hard rules

- Never emit a BLOCKED verdict without listing specific blocking issues
- Never emit PUBLISH without having checked all pages in scope
- If `--dry-run`: emit assessment only; do not invoke fix skills
