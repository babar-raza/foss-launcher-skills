# TC-INDEX — Parity Migration Taskcard Index

**Generated**: 2026-05-15  **Plan**: PAR-012

## Summary

Total taskcards: 76

## Wave Order

| Wave | Domain Prefix | Description |
|------|--------------|-------------|
| W1 | CF, VF-001 | Safety + configuration |
| W2 | RG | Registry + ID mapping |
| W3 | GV | Governance documentation |
| W4 | LB | Shared library stubs |
| W5 | CI-001..007 | CI checks: skill_governance priority |
| W6 | SC | Backing script implementations |
| W7 | SK | Skill content updates |
| W8 | CI-008+ | CI checks: remaining domains |
| W9 | TS | Test coverage additions |
| W10 | VF-002, DC | Verification + closure |

## Full Taskcard List

| TC ID | Title | Domain | Status |
|-------|-------|--------|--------|
| CF-001 | Create .env.example with all required env vars | CF | pending |
| VF-001 | Add CONTENT_REPO_PATH safety guard to test suite | VF | pending |
| VF-002 | Run full parity verification and update parity-matrix.md | VF | pending |
| RG-001 | Verify docs/id-mapping.md completeness for all 84 aspose.org skills | RG | pending |
| GV-001 | Port evidence governance doc from aspose.org | GV | pending |
| GV-002 | Port write boundaries doc from aspose.org | GV | pending |
| GV-003 | Port launch gates doc from aspose.org | GV | pending |
| GV-004 | Port naming conventions doc from aspose.org | GV | pending |
| GV-005 | Port DAR policy doc from aspose.org | GV | pending |
| GV-006 | Port docs/workflows/causal-backtracking.md | GV | pending |
| GV-007 | Port docs/workflows/change-trigger-matrix.md | GV | pending |
| GV-008 | Port docs/workflows/claim-injection.md | GV | pending |
| GV-009 | Port docs/workflows/completion-verification.md | GV | pending |
| GV-010 | Port docs/workflows/evaluator-changes.md | GV | pending |
| GV-011 | Port docs/workflows/forced-validation.md | GV | pending |
| GV-012 | Port docs/workflows/gap-escalation.md | GV | pending |
| LB-001 | Create scripts/pipeline/lib/grade_writer.py stub | LB | pending |
| LB-002 | Create scripts/pipeline/lib/heal_controller.py stub | LB | pending |
| LB-003 | Create scripts/pipeline/lib/provenance.py stub | LB | pending |
| LB-004 | Create scripts/pipeline/lib/registry_loader.py stub | LB | pending |
| LB-005 | Create scripts/pipeline/lib/content_patcher.py stub | LB | pending |
| LB-006 | Create scripts/pipeline/lib/audit_runner.py stub | LB | pending |
| LB-007 | Create scripts/pipeline/lib/evidence_runner.py stub | LB | pending |
| LB-008 | Create scripts/pipeline/lib/backtrack_resolver.py stub | LB | pending |
| CI-001 | Port skill_governance CI checks (14 checks) | CI | pending |
| CI-002 | Port content_quality CI checks (6 checks) | CI | pending |
| CI-003 | Port pipeline_integrity CI checks (7 checks) | CI | pending |
| CI-004 | Port provenance CI checks (5 checks) | CI | pending |
| CI-005 | Port knowledge CI checks (3 checks) | CI | pending |
| CI-006 | Port metrics CI checks (6 checks) | CI | pending |
| CI-007 | Port locale CI checks (1 checks) | CI | pending |
| CI-008 | Port link_integrity CI checks (1 checks) | CI | pending |
| CI-009 | Port other CI checks (19 checks) | CI | pending |
| SC-001 | Implement backing script for knowledge-diff | SC | pending |
| SC-002 | Implement backing script for stale-detect | SC | pending |
| SC-003 | Implement backing script for page-plan | SC | pending |
| SC-004 | Implement backing script for page-draft | SC | pending |
| SC-005 | Implement backing script for page-update | SC | pending |
| SC-006 | Implement backing script for page-enhance | SC | pending |
| SC-007 | Implement backing script for cross-platform | SC | pending |
| SC-008 | Implement backing script for gap-plan | SC | pending |
| SC-009 | Implement backing script for gap-apply | SC | pending |
| SC-010 | Implement backing script for blog-migrate | SC | pending |
| SC-011 | Implement backing script for pipeline-harden | SC | pending |
| SK-001 | Update skill content: backlog (+50.3KB gap) | SK | pending |
| SK-002 | Update skill content: manual-edit (+16.5KB gap) | SK | pending |
| SK-003 | Update skill content: section-enhance (+14.1KB gap) | SK | pending |
| SK-004 | Update skill content: publish-readiness-review (+13.9KB gap) | SK | pending |
| SK-005 | Update skill content: commit (+13.7KB gap) | SK | pending |
| SK-006 | Update skill content: plan-normalize (+9.6KB gap) | SK | pending |
| SK-007 | Update skill content: system-heal (+8.7KB gap) | SK | pending |
| SK-008 | Update skill content: refresh-product (+8.4KB gap) | SK | pending |
| SK-009 | Update skill content: page-update (+8.2KB gap) | SK | pending |
| SK-010 | Update skill content: evidence-enhance (+7.1KB gap) | SK | pending |
| SK-011 | Update skill content: evidence-repair (+6.7KB gap) | SK | pending |
| SK-012 | Update skill content: new-reference-page (+6.6KB gap) | SK | pending |
| SK-013 | Update skill content: heal-page (+6.5KB gap) | SK | pending |
| SK-014 | Update skill content: batch-reference (+5.3KB gap) | SK | pending |
| SK-015 | Update skill content: embed-knowledge (+4.7KB gap) | SK | pending |
| SK-016 | Update skill content: gap-apply (+4.7KB gap) | SK | pending |
| SK-017 | Update skill content: truth-index (+4.6KB gap) | SK | pending |
| SK-018 | Update skill content: new-blog-post (+4.3KB gap) | SK | pending |
| SK-019 | Update skill content: truth-audit-content (+4.1KB gap) | SK | pending |
| SK-020 | Update skill content: session-start (+4.0KB gap) | SK | pending |
| SK-021 | Batch update remaining 32 skill content files | SK | pending |
| SK-031 | Port missing skill: blog-migrate (7.65KB) | SK | pending |
| SK-032 | Port missing skill: pipeline-harden (18.6KB) | SK | pending |
| TS-001 | Add test coverage for batch-eval-fix | TS | pending |
| TS-002 | Add test coverage for batch-remediate | TS | pending |
| TS-003 | Add test coverage for change-guard | TS | pending |
| TS-004 | Add test coverage for cleanroom-regen | TS | pending |
| TS-005 | Add test coverage for content-audit | TS | pending |
| TS-006 | Add test coverage for embed-knowledge | TS | pending |
| TS-007 | Add test coverage for evidence-cite | TS | pending |
| TS-008 | Add test coverage for knowledge-enrich | TS | pending |
| TS-009 | Add test coverage for truth-merge | TS | pending |