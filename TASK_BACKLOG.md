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
