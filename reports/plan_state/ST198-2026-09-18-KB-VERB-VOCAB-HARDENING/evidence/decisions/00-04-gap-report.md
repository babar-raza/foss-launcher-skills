SKILL GAP ESCALATION
Task: ST-198 -- give the KB slug verb/noun parser (site_planner.py's _VERB_KEYWORDS-derived
  reverse lookup used by _validate_kb_slugs() and mirrored in
  content_eval/evaluators/topic_grounding.py's _extract_topic_noun()) one shared implementation
  and a correct vocabulary (verb-synonym rows recognised in reverse, category-hint rows never
  treated as verbs), guard Check 2 against an empty parsed verb, and bump
  EVALUATOR_VERSIONS["topic_grounding"] in the same change set. Full plan:
  <local-plan-cache>/create-a-format-plan-playful-sparkle.md.
Capability state: NONE
Skills invoked (completed): none -- this is a repo-internal pipeline-code hardening task
  (parser correctness + de-duplication across two library modules and their own test files),
  not a content/knowledge/product-launch task any registered skill chain targets.
Uncovered requirement: editing scripts/pipeline/commands/launch/site_planner.py,
  scripts/pipeline/content_eval/evaluators/topic_grounding.py,
  scripts/pipeline/content_eval/__init__.py, and their own test files
  (scripts/pipeline/tests/test_site_planner.py,
  scripts/pipeline/tests/content_eval/test_topic_grounding.py). Checked the candidates the plan's
  own research already ruled out:
    - S-73 manual-edit: excludes scripts/pipeline/** by design (content-only skill).
    - S-99 pipeline-harden: preconditions (clone cache, non-stale knowledge model,
      family/platform launch_gate) are structurally inapplicable to a parser-correctness fix
      with no product/family/platform axis.
    - S-62 batch-reference: unrelated domain (bulk reference-page content generation); would
      hard-fail its own DAR prerequisite for a task with no product/knowledge target.
  No other registered skill's scope covers a shared-library parsing-logic fix spanning
  commands/launch/ and content_eval/evaluators/.
Impact: without this, the fix either cannot proceed (blocked on a nonexistent skill) or would
  require an ungoverned ad hoc edit to a governed pipeline-ops path, which the skill-context
  PreToolUse hook (scripts/ci/hooks/check_skill_context_hook.sh) actively blocks by construction
  for any file under scripts/pipeline/* with no active skill context.

ENHANCEMENT PLAN
  Title: n/a -- disposition below is `bounded-oneoff`, not `recurring-candidate`; no new skill ID
    is proposed. This is a one-shot correctness fix to existing parsing logic, not a repeatable,
    parameterizable deliverable that would produce a report artifact on every future invocation.
  Proposed skill ID: n/a
  Input: n/a
  Output: n/a
  Skill file: n/a
  Estimated complexity: LOW-MEDIUM (5 files, additive + one refactor, full plan with 37 taskcards
    and 201 micro-steps already exists and was independently reviewed and repaired).
  Workaround: YES -- skill_context.py gap-approved context, scoped to exactly the 5 files this
    plan's implementation cards touch (plus test_site_planner_kb.py is explicitly read-only /
    excluded from the scope, since its role is to detect regressions in this exact area).

DISPOSITION
  Disposition: bounded-oneoff (per docs/workflows/gap-escalation.md's rubric: a small,
    first-occurrence, bounded code/config patch to two existing modules + their own test files;
    not a new repeatable report-producing deliverable in its own right).
  Routed via: `skill_context.py gap --task "ST-198: KB slug verb vocabulary hardening" --report
    reports/skill-gaps/2026-09-18-st198-kb-verb-vocabulary.md --scope
    "scripts/pipeline/commands/launch/site_planner.py,scripts/pipeline/content_eval/evaluators/topic_grounding.py,scripts/pipeline/content_eval/__init__.py,scripts/pipeline/tests/test_site_planner.py,scripts/pipeline/tests/content_eval/test_topic_grounding.py"
    --session-id $AGENT_SESSION_ID`
  Precedent: commit a7c055c14ddea9612dd6a98eb2931ca3e626c010 (TC-GOV-01-01), same routing
    mechanism (`skill_context.py gap` + `git_plumb_commit.py --skills GAP-APPROVED`), for an
    analogous scripts/pipeline/** correctness fix with no registered skill covering the file.
  Authorization: user-authored, independently-reviewed plan
    (<local-plan-cache>/create-a-format-plan-playful-sparkle.md), executed on the
    user's explicit "execute as per Single-go execution prompt" instruction, 2026-09-23.
  Status: open (this session, resolved via skill_context.py gap + direct implementation per the
    plan's taskcards; see reports/plan_state/ST198-2026-09-18-KB-VERB-VOCAB-HARDENING/taskcards.jsonl
    for verification evidence).
