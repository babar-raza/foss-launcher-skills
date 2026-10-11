## Mission: MT064-2026-09-05-SEO-KEYWORD-UTILIZATION-ENGINE
> Predecessor mission: `seo-keyword-production-integration`
> Investigation/plan file: `C:/Users/prora/.claude/plans/investigate-how-to-best-cozy-pizza.md`
> Status: **OPEN, IN PROGRESS** (45/81 taskcards CLOSED, 35 READY, 1 IN_PROGRESS as of
> last check 2026-09-10)
> Mission contract: registered via the durable archive path (GOV-02 retroactive
> registration rule, `MT062` precedent) — root `MISSION_AUTHORITY.yaml` was held by
> `MT058` at mission-open time. `mission_locked: true` in its own archive record.
> Durable taskcards: `reports/plan_state/MT064-2026-09-05-SEO-KEYWORD-UTILIZATION-ENGINE/taskcards.jsonl`
> (81 unique task ids)

### Context

Resumes `seo-keyword-production-integration` at its real state (33/68 CLOSED at
hand-off), repairing two live measurement defects found by investigation on
2026-09-05 — F1: `keywords/` working tree had been rolled back to older-than-HEAD
data across 11 files; F2: `map_url.py` resolved URLs with exact-case `Path.exists()`
while Hugo lowercases slugs and reference filenames are PascalCase, making all 7
`reference.aspose.org` URLs at HEAD unresolvable — then builds the v13 Keyword
Utilization Engine (Contracts A–J) plus 14 v12 platform-hardening tasks and
`title_clause_composer.py`, through a self-pacing `/loop`, ending with one governed,
observed pilot of description/title changes on the highest-impression pages.
Executed with every review/clearance/rollback gate as an independent reviewer Agent
per AGENTS.md §7c and explicit 2026-09-05 operator direction that no human is a
scheduled gate inside implementation or verification.

### Scope (in progress)

- F1/F2 fixed with regression tests; a fresh SEO pipeline baseline run
  (validate/inventory/map_url/analyze/recommend/safety/report) after the fix.
- 10 Keyword Utilization Engine modules (Contracts A–J: `keyword_intent.py`,
  `keyword_page_assignment.py`, `description_composer.py`, `naturalness_evaluator.py`,
  `metadata_consistency.py`, `change_budget.py`, `observe_experiments.py`,
  `metadata_rollback.py`, `autonomy_state.py`, `execution_invariants.py`) plus
  `title_clause_composer.py`, wired into the existing SEO pipeline
  (`analyze.py`/`recommend.py`/`safety.py`).
- An autonomy state machine (Contract I) and 14 execution invariants (Contract J,
  each with a passing negative test) live before any content write.
- One frozen pilot cohort (title on 1 KB/FAQ page; description on ≤10 high-impression
  English pages) written through `apply.py` after independent-reviewer-agent
  clearance, followed by an observation window against real GSC weekly-snapshot
  metrics.
- A plan-only deliverable (not execution) for the duplicate-`<title>`-tag remediation
  campaign (F13; 1,097 groups / 10,402 pages).

### Deliberately out of scope

Executing the duplicate-title backfill campaign itself (plan only); any
`themes/kb/` removal; any body-prose edit (writable surface is frontmatter
description/seoTitle/keywords only, via `apply.py`); any Schema A LLM cost-policy
change; `www.aspose.org` brand-query work.

### Status as of last check

In progress — this session's own working tree shows `scripts/seo/pipeline/description_composer.py`
and `title_clause_composer.py` (plus their tests) modified, consistent with this
mission's ongoing execution. Recent commit history includes multiple `fix(seo):`
reworks tagged with this mission's iteration numbers (e.g. `MT064 it-0061`,
`it-0060`, `it-0055`) — the mission has not been formally closed and this file does
not claim a final outcome.
