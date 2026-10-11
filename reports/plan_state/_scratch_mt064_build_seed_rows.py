"""One-off generator for the MT064 ledger seed JSON (SEO-LEDGER-RECONCILE-V15).
Scratch script under reports/plan_state/ (gitignored, tier-1 writable) --
matches this directory's existing _scratch_*.py precedent. Not committed;
writes to a scratch temp file consumed by taskcard_cli.py seed, which is the
actual ledger-write surface."""
import json
import sys

# task_id -> (priority, wave, dependencies[full ids], allowed_paths, stage_limit, title)
ROWS = [
    ("SEO-MISSION-REREGISTER", "P0", 0, [],
     ["reports/plan_state/<MID>/mission_authority.yaml", "reports/skill-gaps/2026-09-05-seo-keyword-utilization-engine.md", "reports/evidence/<MID>/it-0000/"],
     "READY->CLOSED same iteration", "Mint MT0NN, archive mission record, file gap report, record baseline"),
    ("SEO-LOOP-TASKCARD-CLI", "P0", 0, ["SEO-MISSION-REREGISTER"],
     ["scripts/pipeline/commands/governance/taskcard_cli.py", "scripts/pipeline/tests/test_taskcard_cli.py"],
     "INTEGRATION_VERIFIED", "Thin CLI wrapper over TaskcardStore"),
    ("SEO-KEYWORDS-WORKTREE-RESTORE", "P0", 0, ["SEO-MISSION-REREGISTER"],
     ["keywords/", "data/seo_schema_a_migration_state.json"],
     "CLOSED", "Restore keywords/ worktree to HEAD (F1)"),
    ("SEO-LEDGER-RECONCILE-V15", "P0", 0, ["SEO-LOOP-TASKCARD-CLI"],
     ["reports/plan_state/<MID>/taskcards.jsonl", "plans/investigate-how-to-best-cozy-pizza.md", "backlog/inbox.md"],
     "CLOSED", "Seed the ledger, close reconciled predecessor rows, fix stale doc claims"),
    ("SEO-PLAN-NORMALIZE-G1", "P0", 0, ["SEO-LEDGER-RECONCILE-V15"],
     [], "CLOSED", "Normalize + freeze the plan contract, lock the mission"),

    ("SEO-MAPURL-CASE-INSENSITIVE-RESOLVE", "P0", 1, ["SEO-PLAN-NORMALIZE-G1"],
     ["scripts/seo/pipeline/map_url.py", "scripts/seo/tests/test_map_url_resolution.py", "scripts/seo/tests/conftest.py"],
     "END_TO_END_VERIFIED", "Case-fold URL resolution so PascalCase reference filenames match lowercased Hugo slugs (F2)"),
    ("SEO-PIPELINE-RERUN-BASELINE", "P0", 1, ["SEO-MAPURL-CASE-INSENSITIVE-RESOLVE", "SEO-KEYWORDS-WORKTREE-RESTORE"],
     ["reports/seo/"], "IMPLEMENTED", "Fresh validate->inventory->map_url->analyze->recommend->safety->report baseline, no apply.py"),
    ("SEO-TITLE-PILOT-OBSERVATION-MEASURE", "P1", 1, ["SEO-PIPELINE-RERUN-BASELINE"],
     ["reports/seo/pilot_observation_2026-09.json", "scripts/seo/pipeline/gsc_history.py"],
     "IMPLEMENTED", "Pre/post pilot-page position+CTR measurement from weekly GSC snapshots (F5)"),
    ("SEO-TESTS-CI-WIRING", "P1", 1, ["SEO-PLAN-NORMALIZE-G1"],
     ["pytest.ini", ".github/workflows/seo-analysis.yml", "scripts/pipeline/config/registry.yaml"],
     "INTEGRATION_VERIFIED", "Wire scripts/seo/tests into pytest.ini and CI"),
    ("SEO-GSC-COLLECTOR-COVERAGE-AUDIT", "P2", 1, ["SEO-PIPELINE-RERUN-BASELINE"],
     ["reports/evidence/<MID>/"], "IMPLEMENTED", "Explain the 7-URL reference.aspose.org GSC collector coverage gap (F7)"),

    ("SEO-KEYWORD-PAGE-ASSIGNMENT", "P0", 2, ["SEO-MAPURL-CASE-INSENSITIVE-RESOLVE"],
     ["scripts/seo/pipeline/keyword_page_assignment.py", "scripts/seo/pipeline/analyze.py", "scripts/seo/tests/test_keyword_page_assignment.py"],
     "END_TO_END_VERIFIED", "Contract B: cross-site union index, cannibalization gate"),
    ("SEO-SCHEMA-A-DUAL-FIELD-GENERATION", "P1", 2, ["SEO-PLAN-NORMALIZE-G1"],
     ["scripts/seo/get_keywords.py", "scripts/seo/pipeline/validate.py", "scripts/seo/pipeline/check_merge_safety.py", "scripts/seo/tests/"],
     "INTEGRATION_VERIFIED", "title_ready_variant + schema_version:2, lazy/additive"),
    ("SEO-KEYWORD-INTENT-CONTRACT", "P0", 2, ["SEO-SCHEMA-A-DUAL-FIELD-GENERATION"],
     ["scripts/seo/pipeline/keyword_intent.py", "scripts/seo/pipeline/recommend.py", "scripts/seo/pipeline/safety.py", "scripts/seo/tests/test_keyword_intent.py", "reports/seo/intent_llm_cache.json"],
     "END_TO_END_VERIFIED", "Contract A: deterministic-first intent parser, cached LLM fallback"),
    ("SEO-STATE-MANIFEST", "P2", 2, ["SEO-PLAN-NORMALIZE-G1"],
     ["scripts/seo/pipeline/pipeline_state.py", "reports/seo/pipeline_state.json", "scripts/seo/tests/"],
     "INTEGRATION_VERIFIED", "Versioned additive index of every seo state file"),
    ("SEO-RECOMMENDATION-MEMORY", "P1", 2, ["SEO-STATE-MANIFEST"],
     ["scripts/seo/pipeline/recommendation_memory.py", "scripts/seo/pipeline/recommend.py", "reports/seo/recommendation_memory.json"],
     "INTEGRATION_VERIFIED", "Cache keyed (page_path, field, grounded_source_hash), fail-open-loud"),
    ("SEO-METADATA-NATURALNESS-EVALUATOR", "P1", 2, ["SEO-KEYWORD-INTENT-CONTRACT"],
     ["scripts/seo/pipeline/naturalness_evaluator.py"], "END_TO_END_VERIFIED", "Contract D: Stage A/B naturalness gates"),
    ("SEO-DESCRIPTION-COMPOSER", "P1", 2, ["SEO-KEYWORD-INTENT-CONTRACT", "SEO-RECOMMENDATION-MEMORY", "SEO-METADATA-NATURALNESS-EVALUATOR"],
     ["scripts/seo/pipeline/description_composer.py", "scripts/seo/pipeline/recommend.py"],
     "END_TO_END_VERIFIED", "Contract C: token-overlap grounded description composer"),
    ("SEO-TITLE-CLAUSE-COMPOSER", "P1", 2, ["SEO-METADATA-NATURALNESS-EVALUATOR", "SEO-SCHEMA-A-DUAL-FIELD-GENERATION"],
     ["scripts/seo/pipeline/title_clause_composer.py", "scripts/seo/pipeline/title_templates.py"],
     "END_TO_END_VERIFIED", "Skeleton-only fallback title clause composer"),
    ("SEO-PAGE-METADATA-CONSISTENCY", "P1", 2, ["SEO-DESCRIPTION-COMPOSER", "SEO-TITLE-CLAUSE-COMPOSER"],
     ["scripts/seo/pipeline/metadata_consistency.py", "scripts/seo/pipeline/safety.py"],
     "INTEGRATION_VERIFIED", "Contract E: WARN-only consistency, routes to requires_human_review"),

    ("SEO-PER-PRODUCT-COMMIT-REVIEW", "P0", 3, [],
     ["reports/plan_state/<MID>/product_review_log.jsonl"],
     "INDEPENDENTLY_REVIEWED per product; CLOSED when all 12 carry a verdict",
     "Independent-reviewer-agent per-product commit-scope clearance"),
    ("SEO-AUTONOMY-STATE-MACHINE", "P0", 3, ["SEO-PER-PRODUCT-COMMIT-REVIEW"],
     ["scripts/seo/pipeline/autonomy_state.py", "data/seo_autonomy_state.json", "scripts/seo/pipeline/apply.py", "scripts/seo/get_keywords.py"],
     "INTEGRATION_VERIFIED (module)", "Contract I: per-(family,mechanism) autonomy grants"),
    ("SEO-CHANGE-BUDGET-GUARD", "P1", 3, ["SEO-APPLY-HARDEN", "SEO-SCHEMA-A-WORKFLOW-UPDATE"],
     ["scripts/seo/pipeline/change_budget.py", "scripts/seo/config/change_budgets.yaml", "scripts/seo/pipeline/check_merge_safety.py", "scripts/seo/pipeline/apply.py"],
     "INTEGRATION_VERIFIED", "Contract G: static caps + warm-up + cross-mechanism weekly counter"),
    ("SEO-WORKFLOW-DRIFT-DETECTION", "P1", 3, ["SEO-PLAN-NORMALIZE-G1"],
     ["scripts/seo/workflows/", "scripts/ci/checks/check_workflow_drift.py", "data/workflow_deploy_baselines.json"],
     "INTEGRATION_VERIFIED", "Track untracked workflow templates, 3-way drift classification (F10)"),
    ("SEO-LLM-METRICS-UNIFY", "P1", 3, ["SEO-PLAN-NORMALIZE-G1"],
     ["scripts/seo/get_keywords.py", "scripts/seo/migrate_platform_labels.py", "scripts/seo/review_keywords.py", "scripts/pipeline/config/metrics_callsite_registry.yaml"],
     "INTEGRATION_VERIFIED", "Gemini call sites emit MetricsEvent (AGENTS.md 15)"),
    ("SEO-HEALTH-SUMMARY", "P2", 3, ["SEO-LLM-METRICS-UNIFY", "SEO-STATE-MANIFEST"],
     ["scripts/seo/pipeline/health_summary.py", "reports/seo/health_summary.md"],
     "IMPLEMENTED", "Includes Contract F disposition breakdown"),
    ("SEO-EXECUTION-INVARIANTS", "P0", 3, ["SEO-KEYWORD-PAGE-ASSIGNMENT", "SEO-CHANGE-BUDGET-GUARD", "SEO-AUTONOMY-STATE-MACHINE", "SEO-WORKFLOW-DRIFT-DETECTION", "SEO-RECOMMENDATION-MEMORY"],
     ["scripts/seo/pipeline/execution_invariants.py", "scripts/seo/pipeline/apply.py", "scripts/seo/pipeline/recommend.py"],
     "END_TO_END_VERIFIED", "Contract J: 14 invariants, one negative test each"),

    ("SEO-S116-DECISION-TABLE-REFRESH", "P1", 4, ["SEO-PLAN-NORMALIZE-G1"],
     ["skills/seo-review.md", ".claude/commands/seo-review.md", ".agents/skills/seo-review/SKILL.md", ".kilocode/skills/seo-review/SKILL.md"],
     "CLOSED", "Activate S-116 decision-table rows 2/3 (F8)"),
    ("SEO-TITLE-PILOT-BACKFILL-KB-FAQ", "P1", 4, ["SEO-TITLE-CLAUSE-COMPOSER", "SEO-S116-DECISION-TABLE-REFRESH", "SEO-EXECUTION-INVARIANTS", "SEO-PER-PRODUCT-COMMIT-REVIEW"],
     ["content/kb.aspose.org/en/pdf/python/faq.md"], "PILOT_PROVEN",
     "1-file title pilot via apply.py; requires pdf CLEARED in product_review_log.jsonl (verify the real row, not just this dependency, before writing)"),
    ("SEO-TITLE-EXPAND-BEYOND-PILOT", "P2", 4, ["SEO-TITLE-PILOT-OBSERVATION-MEASURE", "SEO-AUTONOMY-STATE-MACHINE"],
     ["per-cohort, via apply.py only"], "PILOT_PROVEN",
     "Widen title pilot; requires SEO-TITLE-PILOT-OBSERVATION-MEASURE's verdict to be PASS, not merely CLOSED -- check the verdict file, not just status"),
    ("SEO-DESCRIPTION-PILOT-HIGH-IMPRESSION", "P1", 4, ["SEO-DESCRIPTION-COMPOSER", "SEO-PAGE-METADATA-CONSISTENCY", "SEO-EXECUTION-INVARIANTS", "SEO-S116-DECISION-TABLE-REFRESH", "SEO-PER-PRODUCT-COMMIT-REVIEW"],
     ["content/reference.aspose.org/en/slides/net/SaveFormat.md", "(frozen cohort, <=10 English pages, description field only, via apply.py)"],
     "PILOT_PROVEN", "First real production write of the mission; requires each cohort family CLEARED, not just PER-PRODUCT-COMMIT-REVIEW closed overall"),
    ("SEO-METADATA-OBSERVATION-LOOP", "P1", 4, ["SEO-STATE-MANIFEST", "SEO-EXECUTION-INVARIANTS", "SEO-TITLE-PILOT-OBSERVATION-MEASURE"],
     ["scripts/seo/pipeline/observe_experiments.py", "reports/seo/metadata_experiments.json", "scripts/seo/pipeline/apply.py"],
     "INTEGRATION_VERIFIED", "Contract H: observation window, control group, INCONCLUSIVE extension"),
    ("SEO-METADATA-ROLLBACK", "P1", 4, ["SEO-METADATA-OBSERVATION-LOOP", "SEO-AUTONOMY-STATE-MACHINE"],
     ["scripts/seo/pipeline/metadata_rollback.py"], "INTEGRATION_VERIFIED",
     "Rollback candidates only; revert decision by a fresh reviewer Agent"),
    ("SEO-OBSERVATION-LIVENESS-CHECK", "P1", 4, ["SEO-METADATA-OBSERVATION-LOOP", "SEO-TOKEN-LIVENESS-CHECK"],
     [".github/workflows/seo-analysis.yml"], "INTEGRATION_VERIFIED", "Liveness check step for the observation workflow"),

    ("SEO-REVIEW-ARBITER-RETIRE", "P1", 5, [],
     ["scripts/seo/workflows/seo-review.yml", "scripts/seo/README.md"], "CLOSED",
     "Retire the dead SEO PR Review arbiter workflow (F66); DGR + external gh action"),
    ("SEO-SECRETS-ROTATION-POLICY", "P1", 5, [],
     ["scripts/seo/README.md", "docs/reference/"], "IMPLEMENTED", "Document GOOGLE_API_KEY rotation policy"),
    ("SEO-TOKEN-LIVENESS-CHECK", "P1", 5, ["SEO-SECRETS-ROTATION-POLICY"],
     ["scripts/seo/workflows/seo-token-liveness.yml"], "END_TO_END_VERIFIED", "Total-failure-fallback token liveness workflow"),
    ("SEO-APPLY-PIPELINE-REF-PIN", "P2", 5, ["SEO-WORKFLOW-DRIFT-DETECTION"],
     ["scripts/seo/workflows/seo-apply.yml", "data/seo_pipeline_last_known_good_sha.txt"], "IMPLEMENTED",
     "Fix dead check_audit_results.py path + pin ref (F10)"),
    ("SEO-E2E-PIPELINE-TEST", "P2", 5, ["SEO-TESTS-CI-WIRING"],
     ["scripts/seo/tests/test_e2e_pipeline.py"], "INTEGRATION_VERIFIED", "Isolated temp-copy end-to-end pipeline test"),
    ("SEO-LOGGING-CONSISTENCY", "P3", 5, [],
     ["scripts/seo/pipeline/*.py (logging only)"], "IMPLEMENTED", "Logging consistency pass"),
    ("SEO-FAMILY-REGISTRY-DRIFT-DETECTION", "P1", 5, [],
     ["scripts/ci/checks/check_family_registry_drift.py"], "INTEGRATION_VERIFIED", "Detect family-registry drift (F70)"),
    ("SEO-KEYWORDS-FRONTMATTER-WRITE-PATH", "P2", 5, ["SEO-EXECUTION-INVARIANTS", "SEO-S116-DECISION-TABLE-REFRESH"],
     ["scripts/seo/pipeline/frontmatter_grounding.py"], "PILOT_PROVEN", "KB-only keywords: frontmatter write path (F6)"),
    ("SEO-EXTERNAL-RETIREMENT-GATE-CHECK", "P2", 5, ["SEO-MAPURL-CASE-INSENSITIVE-RESOLVE"],
     [], "IMPLEMENTED", "Read-only: 3 clean scheduled runs + 1 governed apply gate check (verify the real run history, not just this one dependency)"),
    ("SEO-EXTERNAL-WORKFLOWS-RETIRE-PR", "P2", 5, ["SEO-EXTERNAL-RETIREMENT-GATE-CHECK"],
     ["external PR in Aspose/aspose.org-workflows"], "CLOSED", "External retirement PR, merged after independent review"),
    ("SEO-DUPLICATE-TITLE-CAMPAIGN-PLAN", "P2", 5, ["SEO-TITLE-CLAUSE-COMPOSER"],
     ["reports/plan_state/<MID>/duplicate-title-campaign-proposal.md"], "IMPLEMENTED",
     "Plan-only deliverable for the 1,097-group duplicate-title campaign (F13)"),
    ("SEO-SITE-PLANNER-DEMAND-TIEBREAK-SCHEMA-A", "P2", 5, ["SEO-KEYWORD-INTENT-CONTRACT"],
     ["scripts/seo/pipeline/demand_hints.py", "scripts/seo/tests/test_demand_hints.py"], "INTEGRATION_VERIFIED",
     "Schema A fallback demand tier when Schema B is empty, weighted below Schema B"),
]

CARRIED_FORWARD = [
    ("SEO-APPLY-HARDEN", ["Promoted END_TO_END_VERIFIED -> CLOSED per predecessor-mission reconciliation (2026-09-05): "
      "5 weeks in production (recorded 2026-07-29), apply.py write-path hardening live, "
      "scripts/seo/tests/test_apply_governance.py (15 tests) still present and green as of this session's "
      "focused rerun. See reports/plan_state/seo-keyword-production-integration/taskcards.jsonl for the full "
      "original evidence_refs."]),
    ("SEO-MAPURL-EN-PREFIX-FIX", ["Promoted END_TO_END_VERIFIED -> CLOSED per predecessor-mission reconciliation (2026-09-05): "
      "docs/kb/reference /en/ bare-.md fallback landed 2026-07-29, 6 tests green, 0 regressions on the 130-URL "
      "baseline. See reports/plan_state/seo-keyword-production-integration/taskcards.jsonl for the full original "
      "evidence_refs."]),
    ("SEO-SCHEMA-CLASSIFY-STRUCTURAL-PILOT-VERIFY", ["Promoted END_TO_END_VERIFIED -> CLOSED per predecessor-mission "
      "reconciliation (2026-09-05): schema-classification before/after pilot rerun (2026-07-29) proved zero "
      "regression and +40 previously-discarded Schema B entries recovered. See "
      "reports/plan_state/seo-keyword-production-integration/taskcards.jsonl for the full original evidence_refs."]),
    ("SEO-SCHEMA-A-WORKFLOW-UPDATE", ["F4, independently re-verified live 2026-09-05 in this session: "
      "gh run list --repo Aspose/aspose.org-workflows --workflow seo-keyword-refresh.yml shows run 33312284763 "
      "(schedule trigger) completed/success at 2026-08-30T12:44:19Z; gh pr view 69 --repo Aspose/aspose.org shows "
      "state=MERGED, mergedAt=2026-08-30T13:48:40Z, title='chore(seo): Schema A keyword refresh [2026-08-30]' -- "
      "the unattended scheduled auto-merge v14 flagged as a residual gap is closed."]),
]

out = []
for task_id, priority, wave, deps, allowed_paths, stage_limit, title in ROWS:
    out.append({
        "task_id": task_id,
        "status": "READY",
        "priority": priority,
        "wave": wave,
        "dependencies": deps,
        "allowed_paths": allowed_paths,
        "stage_limit": stage_limit,
        "title": title,
        "source": "investigate-how-to-best-cozy-pizza.md v(2026-09-05 rev2) Task DAG",
        "evidence_refs": [],
    })

for task_id, evidence in CARRIED_FORWARD:
    out.append({
        "task_id": task_id,
        "status": "CLOSED",
        "priority": None,
        "wave": -1,
        "dependencies": [],
        "allowed_paths": [],
        "stage_limit": "CLOSED",
        "title": "carried forward from seo-keyword-production-integration",
        "source": "seo-keyword-production-integration ledger reconciliation",
        "carried_forward_from": "seo-keyword-production-integration",
        "evidence_refs": evidence,
    })

# Overrides for the 3 Wave-0 cards already CLOSED/IN_PROGRESS this session.
STATUS_OVERRIDES = {
    "SEO-MISSION-REREGISTER": ("CLOSED", [
        "reports/plan_state/MT064-2026-09-05-SEO-KEYWORD-UTILIZATION-ENGINE/mission_authority.yaml",
        "reports/skill-gaps/2026-09-05-seo-keyword-utilization-engine.md",
        "reports/evidence/MT064-2026-09-05-SEO-KEYWORD-UTILIZATION-ENGINE/it-0000/head_sha.txt",
    ]),
    "SEO-LOOP-TASKCARD-CLI": ("CLOSED", ["commit:243aaa40d7f1e5b7158ca2ee2cbb359db8775e1d"]),
    "SEO-KEYWORDS-WORKTREE-RESTORE": ("CLOSED", [
        "reports/evidence/MT064-2026-09-05-SEO-KEYWORD-UTILIZATION-ENGINE/it-0000/keywords_restore_sha256_table.csv",
    ]),
    "SEO-LEDGER-RECONCILE-V15": ("IN_PROGRESS", []),
}
for row in out:
    if row["task_id"] in STATUS_OVERRIDES:
        status, ev = STATUS_OVERRIDES[row["task_id"]]
        row["status"] = status
        row["evidence_refs"] = ev

with open(sys.argv[1], "w", encoding="utf-8") as f:
    json.dump(out, f, indent=2)
print(f"wrote {len(out)} rows to {sys.argv[1]}")
