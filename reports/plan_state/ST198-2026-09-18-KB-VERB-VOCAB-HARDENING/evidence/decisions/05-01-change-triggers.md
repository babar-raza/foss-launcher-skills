authoritative_plan: PLAN-ST198-KB-VERB-VOCAB-HARDENING
requirement: REQ-KBV-005, REQ-KBV-009
taskcard: TC-ST198-05-01

# Change-trigger matrix obligations (2026-09-23)

Row (evaluator logic changed) -> "Re-run content_eval for all products with the affected evaluator
category": SATISFIED by TC-ST198-04-02 (full `evaluate all --evaluators topic_grounding`,
9125 pages, before/after diff done).

Row (site_planner.py / delta logic changes) -> "/delta-site-plan (S-82) per affected product":
`detect_kb_verb` is UNCHANGED (golden pin test + fingerprint-equal proof, TC-ST198-02-01); no
generated slug changed for any product (byte-identical stdout for all 33 KB pairs, TC-ST198-04-04,
excluding only the `generated_at:` timestamp line). Since the real production entry point produces
provably identical output, a WRITING `/delta-site-plan` run is not required -- the read-only
`--mode update --dry-run` sweep already performed IS the evidence this row asks for.

Row (EVALUATOR_FREEZE_VERSION bumps) -> GRADE_CONTRACT.md sync: N/A. This change bumps only the
per-evaluator EVALUATOR_VERSIONS["topic_grounding"] entry (1->2), not EVALUATOR_LOGIC_VERSION or
EVALUATOR_FREEZE_VERSION (both remain "19", confirmed unchanged by `check_evaluator_freeze.py`
exit 0 in TC-ST198-05-03).

Docs/skills/agent-sync: N/A -- searched skills/, .claude/commands/, docs/ at plan-authoring time
(see the independent assessment that produced this plan); no skill or doc pins _VERB_KEYWORDS,
detect_kb_verb, _validate_kb_slugs, split_kb_slug_verb_noun, or _KNOWN_VERBS by name (the only
site_planner symbol pinned anywhere is TROUBLE_HOWTO_MIN, unrelated).
