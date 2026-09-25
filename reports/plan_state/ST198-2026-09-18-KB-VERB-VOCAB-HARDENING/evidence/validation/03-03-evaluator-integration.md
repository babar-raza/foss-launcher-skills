authoritative_plan: PLAN-ST198-KB-VERB-VOCAB-HARDENING
requirement: REQ-KBV-002, REQ-KBV-006
taskcard: TC-ST198-03-03

# Evaluator-level integration (2026-09-23)

- Extended scoped set (9 files, 254 tests): 254 passed, 0 failed.
- One-file evaluator run on content/kb.aspose.org/en/email/cpp/how-to-read-msg-files-cpp.md,
  --evaluators topic_grounding: exit 0. Finding: level=FAIL, message names noun 'msg-files'
  (was 'read-msg-files' before this change) -- parser fidelity confirmed. Level is STILL FAIL,
  exactly as the plan states: this is not a fix for that page (F-5, CE-02 lexical gap, deferred).
- Identity check: content_eval.evaluators.topic_grounding.split_kb_slug_verb_noun IS
  commands.launch.site_planner.split_kb_slug_verb_noun -> True (single shared implementation).
