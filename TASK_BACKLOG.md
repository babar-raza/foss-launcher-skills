# Task Backlog

Generated: 2026-03-31
Branch: main
Baseline: 224 passed, 15 skipped (pre-audit)
Post-Phase-0: 238 passed, 7 failed (pre-existing scout fixture failures — see STATUS.md)

## Workstream 0 — Pre-flight (COMPLETED)
| ID | Task | Owner | Status | Acceptance |
|----|------|-------|--------|-----------|
| WS0-1 | Set up reports infrastructure | Orchestrator | ✅ DONE | PLAN_SOURCES.md, PLAN_INDEX.md exist |
| WS0-2 | Baseline tests (224p/15s) | Orchestrator | ✅ DONE | 224 passed, 0 failed |
| WS0-3 | Create branch import/aspose-improvements | Orchestrator | ✅ DONE | Branch merged to main |
| WS0-4 | Verify aspose.org repo accessible | Orchestrator | ✅ DONE | scripts/pipeline/ visible |

## Workstream P0 — Phase 0 Quick Wins (COMPLETED 2026-03-31)
| ID | Task | Owner | Status | Acceptance |
|----|------|-------|--------|-----------|
| P0-1 | Update AGENTS.md §6: add Phase 1.5 to launch chain | D_docs | ✅ DONE | Phase 1.5 visible in §6 |
| P0-2 | Update AGENTS.md §12: add S-43/S-44/S-45, fix numbering collision | D_docs | ✅ DONE | 35 skills in skill map |
| P0-3 | Update AGENTS.md §12: add validation systems comparison table | D_docs | ✅ DONE | audit.py vs content_eval documented |
| P0-4 | Remove --no-evidence flag from scripts/pipeline/audit.py | B_implementation | ✅ DONE | No --no-evidence in CLI |
| P0-5 | Fix audit.py per-file fail count (include ev_findings in file_findings) | B_implementation | ✅ DONE | Evidence FAILs included in per-file count |
| P0-6 | Fix skills/content-check.md: evidence checks → frontmatter not HTML comments | D_docs | ✅ DONE | No HTML comment checks in content-check.md |
| P0-7 | Update skills/evidence-materialize.md id: S-40 → S-44 | D_docs | ✅ DONE | id: S-44 in frontmatter |
| P0-8 | Update skills/mental-model.md id: S-41 → S-45 | D_docs | ✅ DONE | id: S-45 in frontmatter |

## Workstream P1 — Phase 1 Foundation (COMPLETED 2026-03-31)
| ID | Task | Owner | Status | Acceptance |
|----|------|-------|--------|-----------|
| P1-1 | Create QUICKSTART.md operator guide | D_docs | ✅ DONE | QUICKSTART.md at repo root, 14KB |
| P1-2 | Update README.md: add 3 evidence skills to catalog | D_docs | ✅ DONE | S-43/S-44/S-45 in catalog |
| P1-3 | Update README.md: Phase 1.5 in launch chain | D_docs | ✅ DONE | Phase 1.5 visible in skill chains |
| P1-4 | Update README.md: add validation pipeline section | D_docs | ✅ DONE | audit.py vs content_eval documented |
| P1-5 | Update README.md: skill count 32→35 | D_docs | ✅ DONE | "35 agent skills" in README |
| P1-6 | Update README.md: fix evidence-cite description (frontmatter not HTML) | D_docs | ✅ DONE | No HTML comment mention in skill catalog |

## Workstream P2 — Phase 2 Enforcement (COMPLETED 2026-03-31)
| ID | Task | Owner | Status | Acceptance |
|----|------|-------|--------|-----------|
| P2-1 | Implement scripts/path_guard.py with tests | B_implementation | ✅ DONE | 38/38 tests pass; ALLOW/DENY exit codes |
| P2-2 | Implement scripts/check_setup.py with tests | B_implementation | ✅ DONE | 31/31 tests pass; ERROR/WARN/OK output |
| P2-3 | Implement scripts/ops_log.py (JSONL ops log) | E_ops | ✅ DONE | 24/24 tests pass; append-only JSONL at reports/ops.log |
| P2-4 | Resolve pre-existing scout fixture failures (7 tests) | C_tests | ✅ DONE | 371/371 tests pass; enum_count, dataclass fields, property setters, constants.json all fixed |

## Workstream P3 — Phase 3 Hardening (COMPLETED 2026-03-31)
| ID | Task | Owner | Status | Acceptance |
|----|------|-------|--------|-----------|
| P3-1 | Implement scripts/pre_write.py mandatory audit hook | B_implementation | ✅ DONE | 25/25 tests pass; FAIL on forbidden path or audit finding |
| P3-2 | Integrate pre_write.py into content-writing skills | D_docs | ✅ DONE | All 5 content-writing skills: check_setup.py step 0 + pre_write.py post-condition |
| P3-3 | Write tests/test_e2e_pipeline.py using fixtures | C_tests | ✅ DONE | 8/8 integration tests pass; full chain verified |
| P3-4 | Add checkpoint/resume mechanism to launch-product | B_implementation | ✅ DONE | Checkpoint protocol + step 1.0 check_setup added to launch-product.md |

## Acceptance Criteria (Minimum Ship Bar)

| # | Requirement | Status |
|---|-------------|--------|
| M1 | AGENTS.md §6 shows Phase 1.5 in launch chain | ✅ DONE |
| M2 | Evidence citation format contradiction resolved | ✅ DONE |
| M3 | Operator can complete first-run setup from docs alone | ✅ DONE (QUICKSTART.md) |
| M4 | audit.py double-append / per-file fail count fixed | ✅ DONE |
| M5 | audit.py `--no-evidence` flag removed | ✅ DONE |
| M6 | Relationship between audit.py and content_eval documented | ✅ DONE |
| M7 | S-01 path-guard implemented as script | ✅ DONE (scripts/path_guard.py) |
| M8 | At least one integration test proves pipeline works end-to-end | ✅ DONE (tests/test_e2e_pipeline.py) |
# Orchestrator Protocol Backlog - 2026-05-14

Primary plan: `plans/from_chat/20260514_155101_from_chat_production_readiness_remediation.md`

| ID | Scope | Owner-Agent | Impacted Paths | Acceptance Criteria | Risk | Tests | Docs |
|----|-------|-------------|----------------|---------------------|------|-------|------|
| PRD-001 | Discovery and architecture verification for production-readiness gaps | A_discovery | `skills/`, `scripts/`, `docs/`, `reports/` | Broken paths, wrong entrypoints, and dependency risks are listed with evidence and ranked | Low, read-only | path scans, registry checks | `reports/agents/A_discovery/PRD-001/*` |
| PRD-002 | Installer, distribution, packaging, and moved-path implementation fixes | B_implementation | `install.sh`, `install.ps1`, `tools/distribute.py`, `pyproject.toml`, `scripts/pipeline/commands/knowledge/refresh_knowledge.py` | Install/distribution no longer produce broken command mirrors; moved paths fixed; entrypoints import | Medium, operator-facing install behavior | targeted pytest + validators | changes/evidence artifacts |
| PRD-003 | Tests and verification hardening | C_tests | `tests/`, `scripts/validate_skills.py`, potential validator helpers | Tests cover command-path drift, installer/distribution behavior, and audit gate contract | Medium, may expose existing failures | full pytest + focused tests | evidence artifacts |
| PRD-004 | Documentation and skill contract repair | D_docs | `README.md`, `QUICKSTART.md`, `OPERATOR_GUIDE.md`, `docs/RUNBOOK.md`, `skills/*.md` | Active docs reference real paths and frontmatter evidence policy | Low to medium, broad docs churn | doc path scan + validators | updated docs/specs |
| PRD-005 | Observability, readiness gates, pilots, and final status | E_ops | `reports/STATUS.md`, `reports/CHANGELOG.md`, readiness reports | Pilot commands and evidence prove final readiness or remaining blockers | Low, report-heavy | pilots + validators | status/changelog |

## Workstream PRD-006 — Implementation Fixes (2026-05-15, B_implementation) COMPLETE
| ID | Task | Owner | Status | Acceptance |
|----|------|-------|--------|-----------|
| PRD-006-1 | Fix getting-started.md: `requirements.txt` → `scripts/requirements.txt` | B_implementation | ✅ DONE | Correct path in Step 1 |
| PRD-006-2 | Fix launch-product.md Phase 1.5: S-40→S-44, S-41→S-45 | B_implementation | ✅ DONE | Correct IDs in Phase 1.5a/b |
| PRD-006-3 | Fix RUNBOOK.md: override_manager/session_ledger/skill_run_manager paths | B_implementation | ✅ DONE | Paths match `scripts/pipeline/commands/ops/` |
| PRD-006-4 | Fix registry.yaml S-23 script path → commands/content/audit.py | B_implementation | ✅ DONE | Registry resolves to real file |
| PRD-006-5 | Create `data/products.json` as `[]` | B_implementation | ✅ DONE | File exists, JSON valid |
| PRD-006-6 | Add `requires: translator_backend` to S-99/100/107/101 in registry | B_implementation | ✅ DONE | Registry annotations present |

## Workstream PRD-007 — Documentation Fixes (2026-05-15, D_docs) COMPLETE
| ID | Task | Owner | Status | Acceptance |
|----|------|-------|--------|-----------|
| PRD-007-1 | Rewrite PIPELINE.md to match `scripts/pipeline/commands/*/` structure | D_docs | ✅ DONE | All listed paths exist on disk |
| PRD-007-2 | Add translator backend setup note to RUNBOOK.md translation section | D_docs | ✅ DONE | Operators know backend is optional |
| PRD-007-3 | Add Unix activation path note to OPERATOR_GUIDE.md | D_docs | ✅ DONE | Both Windows/Unix paths documented |
| PRD-007-4 | Initialize `backlog/` with README template | D_docs | ✅ DONE | `backlog/README.md` created |

## Workstream PRD-008 — Verification (2026-05-15, C_tests) COMPLETE
| ID | Task | Owner | Status | Acceptance |
|----|------|-------|--------|-----------|
| PRD-008-1 | Run full pytest suite after implementation changes | C_tests | ✅ DONE | 751 passed, 1 pre-existing failure (non-regression confirmed) |
| PRD-008-2 | Run validate_skills.py, sync_commands, sync_agents checks | C_tests | ✅ DONE | All 3 validators PASS |
| PRD-008-3 | Pilot: verify S-23 registry points to real file | C_tests | ✅ DONE | Path exists; audit_page callable confirmed |
| PRD-008-4 | Fix test_production_readiness_contracts.py: audit_files → audit_page | C_tests | ✅ DONE | 9/9 contracts pass |

## Live TODO
- [x] Materialize chat-derived plan source.
- [x] Update plan index.
- [x] Create agent workspace directories.
- [x] Spawn specialist workstreams (PRD-006, PRD-007, PRD-008).
- [x] Integrate implementation fixes (PRD-006).
- [x] Integrate documentation fixes (PRD-007).
- [x] Run full validators and pilots (PRD-008).
- [x] Complete per-agent self-review and hardening loop.
- [x] Update STATUS.md and CHANGELOG.md.

---

# Parity Migration Verification Program — 2026-05-15

Plan source: `plans/from_chat/20260515_120000_from_chat_parity_migration_verification.md`
Backing recon: `C:\Users\prora\.claude\plans\bright-singing-harbor.md`

## Workstream PAR-009 — Phase 2: aspose.org Skill Inventory (A_discovery)
| ID | Task | Owner | Status | Acceptance |
|----|------|-------|--------|-----------|
| PAR-009-1 | Build normalized inventory for all 84 aspose.org skills (8-layer assessment) | A_discovery | ✅ DONE | reports/parity/aspose-inventory.yaml: 84 entries |
| PAR-009-2 | Map aspose.org's 63 CI checks to skill/capability domains | A_discovery | ✅ DONE | reports/parity/aspose-ci-checks-map.yaml: 63 checks |
| PAR-009-3 | Map aspose.org's 22 governance/workflow docs to topic areas | A_discovery | ✅ DONE | reports/parity/aspose-governance-map.yaml: 22 docs |
| PAR-009-4 | Verify A2: pipeline/config/registry.yaml maps skills to scripts | A_discovery | ✅ DONE | 33/84 skills have script bindings (rest are governance-only) |
| PAR-009-5 | Verify A7: gap-eval profiles don't depend on Hugo paths | A_discovery | ✅ DONE | Not Hugo-specific; uses CONTENT_REPO_PATH pattern |

## Workstream PAR-010 — Phase 3: foss-launcher Skill Inventory (A_discovery)
| ID | Task | Owner | Status | Acceptance |
|----|------|-------|--------|-----------|
| PAR-010-1 | Build normalized inventory for all 92 foss-launcher skills (8-layer assessment) | A_discovery | ✅ DONE | reports/parity/foss-inventory.yaml: 92 entries |
| PAR-010-2 | Map all 58 test files to skills they cover | A_discovery | ✅ DONE | reports/parity/foss-test-coverage-map.yaml: 58 files |
| PAR-010-3 | Verify A3: docs/id-mapping.md completeness | A_discovery | ✅ DONE | 28 skills have test coverage; mapping needs RG-001 verification |
| PAR-010-4 | Verify A8: foss-only skills have no aspose.org equivalents | A_discovery | ✅ DONE | 10 foss-only confirmed; no cross-repo duplicates found |

## Workstream PAR-011 — Phase 4: Parity Analysis (A_discovery)
| ID | Task | Owner | Status | Acceptance |
|----|------|-------|--------|-----------|
| PAR-011-1 | Cross-reference both inventories; build parity matrix | A_discovery | ✅ DONE | reports/parity/parity-matrix.md: 82 shared + 2 aspose-only + 10 foss-only |
| PAR-011-2 | Classify every gap with gap_classification vocabulary | A_discovery | ✅ DONE | reports/parity/gap-report.md: 81 skills with gaps classified |
| PAR-011-3 | Identify where foss-launcher is already better than aspose.org | A_discovery | ✅ DONE | reports/parity/foss-advantages.md: 10 unique skills + 5 infra advantages |
| PAR-011-4 | Map 59 missing CI checks by category and portability | A_discovery | ✅ DONE | gap-report.md CI section; aspose-ci-checks-map.yaml has domain+portability |
| PAR-011-5 | Identify skill content divergence (file size) for 82 shared skills | A_discovery | ✅ DONE | 52 skills with size_divergence flagged in parity-matrix.md |

## Workstream PAR-012 — Phase 5+6: Target Architecture + Taskcards (D_docs)
| ID | Task | Owner | Status | Acceptance |
|----|------|-------|--------|-----------|
| PAR-012-1 | Design target state for each gap category (rationalized, not copy) | D_docs | ✅ DONE | reports/parity/target-architecture.md: 7 gap categories addressed |
| PAR-012-2 | Decide on blog-migrate and pipeline-harden relevance | D_docs | ✅ DONE | pipeline-harden: high relevance (port); blog-migrate: evaluate |
| PAR-012-3 | Decompose every gap into executable taskcards (TC template) | D_docs | ✅ DONE | reports/parity/taskcards/TC-INDEX.md: 76 TCs (CF/VF/RG/GV/LB/CI/SC/SK/TS) |
| PAR-012-4 | Assign priorities and dependencies to all TCs | D_docs | ✅ DONE | TC-INDEX.md has wave order + dependency columns |

## Workstream PAR-013 — Phase 7+8: Implementation + Verification (B/C agents)
| ID | Task | Owner | Status | Acceptance |
|----|------|-------|--------|-----------|
| PAR-013-1a | CF-001: Create .env.example with 19 env vars | B_implementation | ✅ DONE | .env.example at repo root |
| PAR-013-1b | VF-001: CONTENT_REPO_PATH safety guard in tests/conftest.py | C_tests | ✅ DONE | pytest_configure() aborts on forbidden path |
| PAR-013-1c | RG-001: Update docs/id-mapping.md (S-106..109, aspose-only entries) | B_implementation | ✅ DONE | id-mapping.md complete for all 84+10 skills |
| PAR-013-1d | GV-001..005: Port 5 priority governance docs to docs/governance/ | D_docs | ✅ DONE | evidence-and-provenance, write-boundaries, launch-gates, naming-conventions, dar-table |
| PAR-013-2 | Wave 2: Shared library stubs (LB-001..008) | B_implementation | ✅ DONE | provenance.py+freshness_manifest.py ported; path_utils/knowledge_core/heal_policy/llm_router/decision_engine created; 752 tests pass |
| PAR-013-3 | Wave 3: Skill content updates SK-001..021 (size-diverged skills) | B_implementation | PENDING | After PAR-013-2 |
| PAR-013-4 | Wave 4+5: CI check porting CI-001..009 | B_implementation | PENDING | After PAR-013-3 |
| PAR-013-5 | Verification pilots: fixture-based, dry-run, snapshot comparison | C_tests | PENDING | reports/parity/verification-evidence.md; no writes to aspose.org |
| PAR-013-6 | Write closure report | D_docs | PENDING | reports/parity/closure-report.md |

## Live TODO (Parity Program)
- [x] Phase 1 reconnaissance complete (bright-singing-harbor.md)
- [x] from_chat plan materialized
- [x] PLAN_SOURCES.md updated
- [x] PLAN_INDEX.md updated
- [x] TASK_BACKLOG.md updated
- [x] Agent workspaces created (PAR-009 through PAR-013)
- [x] Phase 2: aspose.org inventory built (PAR-009) — 84 skills, 63 CI checks, 22 governance docs
- [x] Phase 3: foss-launcher inventory built (PAR-010) — 92 skills, 58 test files mapped
- [x] Phase 4: parity matrix + gap report (PAR-011) — 82 shared, 52 size gaps, 81 with gaps
- [x] Phase 5+6: target architecture + taskcards (PAR-012) — 76 TCs across 9 domains
- [x] Phase 7 Wave 1 (PAR-013): .env.example, safety guard, id-mapping, 5 governance docs
- [x] Phase 7 Wave 2 (PAR-013): shared library stubs (LB-001..008) — provenance+freshness_manifest ported; 5 new lib/ modules created; 752 tests pass
- [ ] Phase 7 Wave 3+4 (PAR-013): skill content updates + CI checks
- [ ] Phase 8: verification evidence + closure report (PAR-013)

---
