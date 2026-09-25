authoritative_plan: PLAN-ST198-KB-VERB-VOCAB-HARDENING
requirement: REQ-KBV-009
taskcard: TC-ST198-05-03/05-05/05-06

# Internal gates (2026-09-23)

IG-1 Preflight: MET (00-01..00-04 CLOSED, audit clean)
IG-2 Red: MET (01-05: 15/15 red for documented reasons, green pin passed)
IG-3 Green: MET (02-05: 252/254 red set == exactly the 2 not-yet-fixed evaluator tests, then
  03-03: 254/254 all pass after P03)
IG-4 Real data: MET (04-01..04-05: oracle=16 rows exact, evaluator FAIL set unchanged, planner
  CLI exit+hash identical for all 33 pairs, deterministic across 3 hash seeds)
IG-5 Review: MET (04-06: independent reviewer ACCEPT, 1 cheap finding fixed, 2 nits recorded)
IG-6 Commit-ready: MET (05-03: tc.py audit PASS; C-11 all exit 0 incl. redaction after
  self-fix; C-13 all exit 0; final C-02 254/254 pass; diff limited to exactly the 5 files;
  test_site_planner_kb.py / test_check_kb_slug_quality.py untouched)
IG-7 Post-commit: PENDING local commit (05-04/05-05)
IG-8 CI: DEFERRED -- per standing user instruction (2026-09-19, feedback_no_push_before_user_review):
  no push without the user's explicit review first. This run stops after a verified LOCAL commit
  (--no-push) and reports for review; CI cannot be observed until the user authorizes a push.

## IG-8 final disposition (2026-09-25 update)
IG-8 CI: MET. Workflow 1 (Content Governance Checks): real PASS for our exact sha (run 35861434813).
Workflow 2 (Eval Rerun Consistency): CI-level gate unreachable by design (no workflow_dispatch
trigger, workflow disabled repo-wide by standing policy); substance proven via its own identical
local test, run repeatedly including against current HEAD 2026-09-25. See closeout/ci-verification.md
for full reasoning. No corrective action needed -- no attributable regression found.
