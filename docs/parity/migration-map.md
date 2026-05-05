# Phase 2 Migration Map

**Program:** Skill Parity Phase 2 - aspose.org delta since closure report
**Date:** 2026-05-05
**Branch:** parity-phase2-current-state-migration
**Scope:** G-NEW-01 through G-NEW-15 (all gaps since 2026-04-27 closure)

---

## Gap Summary

| Gap # | Description | Priority | Decision | Target Path |
|-------|-------------|----------|----------|-------------|
| G-NEW-01 | cleanroom-regen skill (S-97) absent from foss | P1 | IMPLEMENT | skills/cleanroom-regen.md |
| G-NEW-02 | scripts/pipeline/commands/ architecture absent | P1 | IMPLEMENT | scripts/pipeline/commands/ |
| G-NEW-03 | 83 genuinely new scripts (selective port) | P1 | SELECTIVE (14 ADOPT/ADAPT) | See Section 2 |
| G-NEW-04 | Claims pipeline infrastructure absent | P1 | IMPLEMENT | commands/content/, commands/knowledge/ |
| G-NEW-05 | Kilocode integration layer absent | P2 | DEFER | aspose-site-specific |
| G-NEW-06 | All 80 SKILL.md contracts reference commands/ paths | P2 | PARTIAL UPDATE (15 skills) | skills/ highest priority only |
| G-NEW-07 | seo-review skill absent from foss | P3 | DEFER | deferred (no backing script) |
| G-NEW-08 | translate meta-skill wrapper absent | P3 | DEFER | low priority |
| G-NEW-09 | CI check scripts (54 .py + 19 .sh) | P3 | DEFER | continues G-089 deferral |
| G-NEW-10 | PreToolUse hook matchers (9 hooks) | P3 | DEFER | continues G-090 deferral |
| G-NEW-11 | PreToolUse matchers (.claude/settings.json) | P3 | DEFER | continues G-091 deferral |
| G-NEW-12 | scripts/pipeline/lib/ (27 shared modules) absent | P1 | SELECTIVE (10 modules) | scripts/pipeline/lib/ |
| G-NEW-13 | scripts/pipeline/core/ (10 foundation modules) absent | P1 | SELECTIVE (7 modules) | scripts/pipeline/core/ |
| G-NEW-14 | scripts/pipeline/config/registry.yaml absent | P2 | IMPLEMENT | scripts/pipeline/config/ |
| G-NEW-15 | check_pipeline_registration.py CI enforcement absent | P2 | DEFER | after commands/ stable |

---

## Section 1: commands/ Directory Structure

Target layout in `scripts/pipeline/commands/`:

```
commands/
  content/       audit.py, batch_reference.py, claim_report.py [NEW], cross_platform_audit.py [NEW], remediate.py
  diagnostics/   change_guard.py, check_audit_results.py
  governance/    no_downgrade_guard.py, plan_check.py, skill_context.py [NEW], structural_lock.py [NEW]
  healing/       backtrack_controller.py, dependency_resolver.py, heal_policy.py
  knowledge/     embed.py, enrich.py, index.py, knowledge_core.py, knowledge_coverage.py [NEW], promote.py,
                 refresh_knowledge.py, truth_audit.py
  launch/        launch_gate.py, site_planner.py
  ops/           cleanroom_manifest.py [NEW], cleanroom_regen.py [NEW], content_diff_classifier.py [NEW],
                 editorial_review_classifier.py [NEW], harvest_ledger.py, override_manager.py,
                 post_refresh_verify.py, refresh_review.py [NEW], report_extract.py,
                 selective_revert.py [NEW], session_ledger.py, skill_run_manager.py,
                 stale_detect.py, token_ops.py, update_product_registry.py
```

After moving, flat scripts become thin re-exports for backwards compatibility.

### Flat Script Mapping

| Existing flat path | New commands/ path | Action |
|--------------------|-------------------|--------|
| scripts/pipeline/session_ledger.py | commands/ops/session_ledger.py | MOVE |
| scripts/pipeline/skill_run_manager.py | commands/ops/skill_run_manager.py | MOVE |
| scripts/pipeline/backtrack_controller.py | commands/healing/backtrack_controller.py | MOVE |
| scripts/pipeline/harvest_ledger.py | commands/ops/harvest_ledger.py | MOVE |
| scripts/pipeline/report_extract.py | commands/ops/report_extract.py | MOVE |
| scripts/pipeline/override_manager.py | commands/ops/override_manager.py | MOVE |
| scripts/pipeline/post_refresh_verify.py | commands/ops/post_refresh_verify.py | MOVE |
| scripts/pipeline/dependency_resolver.py | commands/healing/dependency_resolver.py | MOVE |
| scripts/pipeline/launch_gate.py | commands/launch/launch_gate.py | MOVE |
| scripts/pipeline/heal_policy.py | commands/healing/heal_policy.py | MOVE |
| scripts/pipeline/stale_detect.py | commands/ops/stale_detect.py | MOVE |
| scripts/pipeline/truth_audit.py | commands/knowledge/truth_audit.py | MOVE |
| scripts/pipeline/content_audit.py | commands/content/audit.py | MOVE |
| scripts/pipeline/remediate.py | commands/content/remediate.py | MOVE |
| scripts/pipeline/plan_check.py | commands/governance/plan_check.py | MOVE |
| scripts/pipeline/no_downgrade_guard.py | commands/governance/no_downgrade_guard.py | MOVE |
| scripts/pipeline/change_guard.py | commands/diagnostics/change_guard.py | MOVE |
| scripts/pipeline/update_product_registry.py | commands/ops/update_product_registry.py | MOVE |
| scripts/pipeline/enrich.py | commands/knowledge/enrich.py | MOVE |
| scripts/pipeline/refresh_knowledge.py | commands/knowledge/refresh_knowledge.py | MOVE |
| scripts/pipeline/org_scanner.py | commands/launch/site_planner.py | MOVE+RENAME |
| scripts/pipeline/knowledge_core.py | commands/knowledge/knowledge_core.py | MOVE |
| scripts/pipeline/check_audit_results.py | commands/diagnostics/check_audit_results.py | MOVE |
| scripts/pipeline/token_ops.py | commands/ops/token_ops.py | MOVE |
| scripts/pipeline/attach_evidence.py | commands/content/attach_evidence.py | MOVE |
| scripts/pipeline/audit.py | commands/content/audit_legacy.py | MOVE |

---

## Section 2: Script Classification

### ADOPT/ADAPT (14 scripts to port)

| Script (aspose source) | Decision | Foss target | Notes |
|------------------------|----------|-------------|-------|
| ops/cleanroom_regen.py | ADAPT | commands/ops/cleanroom_regen.py | Path resolution + schema paths |
| ops/cleanroom_manifest.py | ADAPT | commands/ops/cleanroom_manifest.py | Same pattern |
| ops/content_diff_classifier.py | ADOPT | commands/ops/content_diff_classifier.py | Pure diff logic |
| ops/editorial_review_classifier.py | ADOPT | commands/ops/editorial_review_classifier.py | Pure review logic |
| ops/selective_revert.py | ADAPT | commands/ops/selective_revert.py | Git subprocess; path adaptation |
| ops/refresh_review.py | ADAPT | commands/ops/refresh_review.py | Import path adaptation |
| governance/skill_context.py | ADAPT | commands/governance/skill_context.py | reports/ path via config_loader |
| content/claim_report.py | ADAPT | commands/content/claim_report.py | merged/claims.json via config_loader |
| knowledge/knowledge_coverage.py | ADAPT | commands/knowledge/knowledge_coverage.py | Knowledge path via config_loader |
| diagnostics/structural_lock.py | ADAPT | commands/governance/structural_lock.py | Path adaptation |
| content/cross_platform_audit.py | ADAPT | commands/content/cross_platform_audit.py | Content path via config_loader |
| content/batch_reference.py | ADAPT | commands/content/batch_reference.py | Updated aspose version |
| governance/check_grade_downgrade.py | ADOPT | scripts/ci/checks/check_grade_downgrade.py | CI check; pure logic |
| governance/check_grade_integrity.py | ADOPT | scripts/ci/checks/check_grade_integrity.py | CI check; pure logic |

### DEFER (aspose-specific or lower priority)

| Script | Reason |
|--------|--------|
| kilocode/* (4 scripts) | AGENTS.md kilocode rules; aspose-specific |
| ops/llm_router.py | Aspose LLM endpoints (professionalize.com) |
| ops/fingerprint_audit.py | Aspose content fingerprint audit |
| ops/page_impact_assess.py | Aspose content impact assessment |
| ops/project_phase_store.py | Aspose project phase tracking |
| ops/check_locale_topology.py | Aspose locale tree checking |
| ops/skill_chain.py | Aspose hooks system skill chain |
| ops/link_validator.py | Aspose content link validation |
| ops/session_logger.py | Extended session logging; aspose ACTIVE.json |
| ops/translation_coverage.py | Aspose translation tracking |

### SKIP (content migration, aspose content-backfill only)

All 15 scripts in migration/ subdir operate on aspose.org/content/ structure; not portable.

---

## Section 3: lib/ and core/ Module Selection

### core/ modules to port (7 of 10)

| Module | Decision | Notes |
|--------|----------|-------|
| core/constants.py | PORT | Global constants; replace aspose-specific paths |
| core/env_loader.py | ADAPT | Replace CONTENT_REPO_PATH with config_loader |
| core/fs.py | PORT | Filesystem helpers; pure logic |
| core/manifest.py | PORT | Manifest helpers; pure logic |
| core/prereqs.py | ADAPT | Prerequisites; repo root detection |
| core/markdown.py | PORT | Markdown utilities; pure logic |
| core/models.py | PORT | Data models; pure dataclasses |
| core/clone_cache.py | SKIP | Aspose clone cache strategy differs |
| core/knowledge.py | SKIP | Aspose content-repo knowledge structure |

### lib/ modules to port (10 of 27)

| Module | Decision | Notes |
|--------|----------|-------|
| lib/cleanroom_scope.py | PORT | Required by cleanroom_regen.py |
| lib/blog_slug_policy.py | PORT | Blog slug enforcement; reusable |
| lib/evidence_verifier.py | PORT | Evidence verification; reusable |
| lib/grade_manifest.py | PORT | Grade manifest; reusable |
| lib/freshness_manifest.py | PORT | Freshness tracking; reusable |
| lib/triage_confirm.py | PORT | Triage confirm helper; reusable |
| lib/reconcile_triage.py | PORT | Triage reconciliation; reusable |
| lib/section_enhance_validator.py | PORT | Section validation; reusable |
| lib/dependency_registry.py | PORT | Dependency registry; reusable |
| lib/provenance.py | PORT | Provenance tracking; reusable |
| lib/decision_engine.py | SKIP | Aspose-specific decision logic |
| lib/kilocode_compliance.py | SKIP | Kilocode-specific |

---

## Section 4: cleanroom-regen Adaptation Design

Source: aspose.org/scripts/pipeline/commands/ops/cleanroom_regen.py
Target: foss-launcher/scripts/pipeline/commands/ops/cleanroom_regen.py

| Pattern | aspose version | foss adaptation |
|---------|---------------|-----------------|
| _REPO_ROOT | parents[4] from ops/ | Keep same (same relative depth) |
| _SCHEMAS_DIR | _REPO_ROOT / data/schemas/cleanroom | Port schemas to foss data/schemas/cleanroom/ |
| Content paths | content/{site}/en/{family}/{platform}/ | config_loader.get_content_root() |
| venv | .venv/Scripts/python | Same in foss |
| skill_context | governance/skill_context.py begin | Port skill_context.py first |
| Phase B S-IDs | S-62, S-57, S-56, S-58, S-61 | All present in foss (see id-mapping.md) |

All 5 dependency skills present in foss-launcher. No blocking dependency gaps.

---

## Section 5: Claims Pipeline Adaptation Design

**claim_report.py:** Replace merged/claims.json path with config_loader.resolve_knowledge_root();
check scripts/verify_claims.py in foss for ClaimValidator/ClaimPolicy equivalents.

**knowledge_coverage.py:** Knowledge root via config_loader.resolve_knowledge_root();
coverage output path via config_loader.

---

## Section 6: SKILL.md Contract Update Priority List

| Skill | New target script path |
|-------|------------------------|
| commit | commands/ops/session_ledger.py |
| launch-product | commands/launch/site_planner.py |
| knowledge-update | commands/knowledge/embed.py |
| embed-knowledge | commands/knowledge/embed.py |
| stale-detect | commands/ops/stale_detect.py |
| causal-backtrack | commands/healing/backtrack_controller.py |
| gap-apply | commands/content/remediate.py |
| truth-merge | commands/knowledge/promote.py |
| truth-index | commands/knowledge/index.py |
| site-plan | commands/launch/site_planner.py |
| batch-reference | commands/content/batch_reference.py |
| content-check | commands/content/audit.py |
| heal-batch | commands/content/remediate.py |
| knowledge-enrich | commands/knowledge/enrich.py |
| cleanroom-regen | NEW skill: skills/cleanroom-regen.md |

---

## Section 7: Confirmed Deferrals

| Gap | Reason |
|-----|--------|
| G-NEW-05 (kilocode) | Site-specific; kilocode rules not applicable to foss standalone |
| G-NEW-07 (seo-review) | No backing script dependency; no P1 user need |
| G-NEW-08 (translate meta) | Meta-wrapper skill; lower priority |
| G-NEW-09 (CI checks) | Continues G-089 deferral; CI structures differ |
| G-NEW-10/11 (PreToolUse) | Continues G-090/091 deferral |
| G-NEW-15 (check_pipeline_registration) | Add to CI after commands/ structure is stable |

---

## Implementation Order

1. commands/ skeleton + __init__.py files
2. core/ and lib/ modules
3. governance/skill_context.py
4. cleanroom-regen backing script + skill file
5. claims pipeline: claim_report.py, knowledge_coverage.py
6. Flat script moves + re-export stubs
7. SKILL.md contract updates (15 skills)
8. registry.yaml script references
9. Smoke tests + import path tests
10. Full verification suite
