# Phase 4-6: Updated Gap Report and Taskcards

**Generated**: 2026-05-29
**Based on**: Existing gap-report.md + live filesystem verification

## True Remaining Gaps (After Infrastructure Verification)

### G1: Missing Skills
| Slug | Priority | Notes |
|------|----------|-------|
| `blog-migrate` (S-100) | LOW | Blog-specific migration; lower relevance for standalone repo |

### G2: Skill Content Depth Gaps
Skills where foss file < 70% aspose file size (requires section-by-section comparison):
| Slug | Size% | Key Missing Elements |
|------|-------|-------------------|
| `backlog` (S-88→S-98) | 8% | Extensive backlog command reference |
| `knowledge-diff` (S-12) | 35% | Detailed step-by-step workflow |
| `knowledge-update` (S-14) | 59% | More detailed pre/post conditions |
| `page-plan` (S-18) | 79% | Section planning workflows |
| `page-draft` (S-19) | 63% | Template selection details |
| `page-update` (S-20) | 31% | Update decision logic |
| `page-enhance` (S-21) | 66% | Enhancement patterns |
| `publish-readiness-review` (S-90→S-95) | 23% | H-gate checklists, review patterns |
| `launch-product` (S-49→S-38) | 85% | Site plan integration details |
| `system-heal` (S-87→S-93) | 31% | System heal workflow details |

### G3: Missing Script Implementations
Skills that need CLI scripts for full parity:
| Slug | Priority | Reason |
|------|----------|--------|
| `page-plan` | HIGH | Content generation foundation |
| `page-draft` | HIGH | Content generation foundation |
| `page-update` | HIGH | Content maintenance chain |
| `page-enhance` | HIGH | Content quality repair |
| `cross-platform` | MEDIUM | Family consistency validation |
| `content-audit` | MEDIUM | Semantic knowledge verification |
| `content-check` | MEDIUM | Pre-commit structural validation |
| `commit` | MEDIUM | Conventional commit workflow |
| `evidence-repair` | MEDIUM | Evidence remediation |
| `manual-edit` | MEDIUM | Targeted edit workflow |

### G4: Portability Status (VERIFY)
| Component | Status | Notes |
|-----------|--------|-------|
| `gap-eval` (S-62) | PORTABLE | Uses `content_repo_adapter.py` - no hardcoded paths |
| `batch-reference` (S-67) | PORTABLE | Uses `content_repo_adapter.py` |
| `stale-detect` (S-13) | PORTED | `scripts/pipeline/commands/knowledge/stale_detect.py` exists |
| `causal-backtrack` (S-79) | PORTED | `scripts/pipeline/commands/healing/backtrack_controller.py` exists |

### G5: Test Coverage Gaps
Skills with scripts but missing tests:
| Slug | Test File Needed |
|------|-----------------|
| `audit.py` (ground-check) | test_audit_units.py |
| `attach_evidence.py` (evidence-cite) | test_attach_evidence_e2e.py |
| `change_guard.py` (change-guard) | test_change_guard_e2e.py |
| `truth_audit.py` (truth-audit) | test_truth_audit_e2e.py |
| `content_audit.py` (content-audit) | test_content_audit_e2e.py |
| `cross_platform_audit.py` (cross-platform) | test_cross_platform_e2e.py |
| `backtrack_controller.py` (causal-backtrack) | test_backtrack_e2e.py |
| `heal_policy.py` (heal-page) | test_heal_policy_e2e.py |
| `remediate.py` (batch-remediate/40/41/42) | test_remediate_e2e.py |

## Taskcards Generated

TC-001: ~~Port pipeline-harden skill (S-99)~~ **COMPLETED**
- Category: SKILL_PORT
- Phase: 1
- Files to create: skills/pipeline-harden.md
- Files to modify: None
- Dependencies: None
- Verification: `python scripts/validate_skills.py` passes

TC-002: **Add page-plan CLI implementation (S-18)**
- Category: SCRIPT_IMPL
- Phase: 1
- Files to create: scripts/pipeline/commands/plan/page_plan.py
- Dependencies: None
- Verification: `pytest tests/test_page_plan.py` passes

TC-003: **Add page-draft CLI implementation (S-19)**
- Category: SCRIPT_IMPL
- Phase: 2
- Files to create: scripts/pipeline/commands/draft/page_draft.py
- Dependencies: TC-002
- Verification: `pytest tests/test_page_draft.py` passes

TC-004: **Add page-enhance CLI implementation (S-21)**
- Category: SCRIPT_IMPL
- Phase: 2
- Files to create: scripts/pipeline/commands/page/enhance_page.py
- Dependencies: None
- Verification: `pytest tests/test_enhance_page.py` passes

TC-005: **Expand test coverage for existing scripts**
- Category: TEST
- Phase: 3
- Files to create: Multiple test files
- Dependencies: None
- Verification: All new tests pass

TC-006: **Create private-api-policy.md for standalone repo**
- Category: DOCS
- Phase: 3
- Files to create: docs/governance/private-api-policy.md
- Dependencies: None
- Verification: Document exists, follows foss conventions

TC-007: **Skill content depth improvements**
- Category: SKILL_ENHANCE
- Phase: 4
- Files to modify: Multiple skills/*.md files
- Dependencies: None
- Verification: Updated skills pass registry check

## Execution Priority

| Priority | Taskcards |
|----------|----------|
| HIGH | TC-002, TC-003, TC-004 |
| MEDIUM | TC-006 |
| LOW | TC-005, TC-007 |