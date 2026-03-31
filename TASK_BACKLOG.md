# Task Backlog

Generated: 2026-03-31
Branch: import/aspose-improvements
Baseline: 224 passed, 15 skipped

## Workstream 0 — Pre-flight
| ID | Task | Owner | Status | Acceptance |
|----|------|-------|--------|-----------|
| WS0-1 | Set up reports infrastructure | Orchestrator | ✅ DONE | PLAN_SOURCES.md, PLAN_INDEX.md exist |
| WS0-2 | Baseline tests (224p/15s) | Orchestrator | ✅ DONE | 224 passed, 0 failed |
| WS0-3 | Create branch import/aspose-improvements | Orchestrator | ✅ DONE | Branch active |
| WS0-4 | Verify aspose.org repo accessible | Orchestrator | ✅ DONE | scripts/pipeline/ visible |

## Workstream 1 — Config Infrastructure
| ID | Task | Owner | Status | Acceptance |
|----|------|-------|--------|-----------|
| WS1-1 | Extend config_loader.py: content_root, knowledge_root, reports_root | B_implementation | 🔄 IN PROGRESS | test_config_loader passes |
| WS1-2 | Update config.yaml with new keys + comments | B_implementation | pending | Keys present with defaults |
| WS1-3 | Update config.schema.json | B_implementation | pending | Schema validates new keys |
| WS1-4 | Update test_config_loader.py | C_tests | pending | All new key tests pass |

## Workstream 2 — Pipeline Core Scripts
| ID | Task | Owner | Status | Acceptance |
|----|------|-------|--------|-----------|
| WS2-1 | Create scripts/pipeline/__init__.py | B_implementation | pending | Package importable |
| WS2-2 | Import token_ops.py, org_scanner.py (unchanged) | B_implementation | pending | Files present |
| WS2-3 | Import + adapt knowledge_core.py | B_implementation | pending | Uses config_loader paths |
| WS2-4 | Import + adapt audit.py | B_implementation | pending | Uses config_loader paths |
| WS2-5 | Import + adapt attach_evidence.py | B_implementation | pending | Uses config_loader paths |
| WS2-6 | Import + adapt change_guard.py | B_implementation | pending | Uses config_loader paths |
| WS2-7 | Import + adapt content_audit.py | B_implementation | pending | Uses config_loader paths |
| WS2-8 | Import + adapt remediate.py | B_implementation | pending | Uses config_loader paths |
| WS2-9 | Replace scout.py (aspose.org version) | B_implementation | pending | Old tests still pass |
| WS2-10 | Replace merge.py (aspose.org version) | B_implementation | pending | Old tests still pass |
| WS2-11 | Replace index.py (aspose.org version) | B_implementation | pending | Old tests still pass |
| WS2-12 | Replace embed.py (aspose.org version) | B_implementation | pending | Old tests still pass |
| WS2-13 | Verify all 224 tests still pass | C_tests | pending | 224+ passed |

## Workstream 3 — Content Eval + Scout Enrichers
| ID | Task | Owner | Status | Acceptance |
|----|------|-------|--------|-----------|
| WS3-1 | Copy content_eval/ package | B_implementation | pending | Package present |
| WS3-2 | Fix content_eval/cli.py import of audit.py | B_implementation | pending | No import error |
| WS3-3 | Copy scout_enrichers/ package | B_implementation | pending | Package present |
| WS3-4 | Wire enrichers into scout.py (optional) | B_implementation | pending | Scout runs without enrichers |

## Workstream 4 — Skills
| ID | Task | Owner | Status | Acceptance |
|----|------|-------|--------|-----------|
| WS4-1 | Replace all 32 existing skill .md files | B_implementation | pending | All files updated |
| WS4-2 | Import 6 new skills | B_implementation | pending | 6 new .md files in skills/ |
| WS4-3 | Run distribute.py | B_implementation | pending | .claude/commands/ regenerated |
| WS4-4 | Verify distributed files | C_tests | pending | All skills in all 3 formats |

## Workstream 5 — Governance & Docs
| ID | Task | Owner | Status | Acceptance |
|----|------|-------|--------|-----------|
| WS5-1 | Import + adapt AGENTS.md | D_docs | pending | No hardcoded aspose.org paths |
| WS5-2 | Import CLAUDE.md (new) | D_docs | pending | File present |
| WS5-3 | Import CODEX.md (new) | D_docs | pending | File present |
| WS5-4 | Update families.yaml (net alias) | D_docs | pending | net and dotnet both listed |
| WS5-5 | Update README.md operator guide | D_docs | pending | content_root documented |

## Workstream 6 — Validation
| ID | Task | Owner | Status | Acceptance |
|----|------|-------|--------|-----------|
| WS6-G1 | All existing tests pass | C_tests | pending | 224+ passed |
| WS6-G2 | New unit tests pass | C_tests | pending | All new tests pass |
| WS6-G3 | Script CLIs --help work | C_tests | pending | No import errors |
| WS6-G4 | Knowledge bootstrap test | C_tests | pending | Knowledge artifacts created |
| WS6-G5 | Audit smoke test | C_tests | pending | Report generated |
| WS6-G6 | Content eval test | C_tests | pending | Evaluators run |
| WS6-G7 | Skill distribution test | C_tests | pending | All skills distributed |
| WS6-G8 | Path isolation test | C_tests | pending | Clear error when unconfigured |
| WS6-G9 | Config root test | C_tests | pending | Scripts find content |
| WS6-G10 | Governance review | D_docs | pending | No hardcoded paths |
| WS6-MERGE | Commit + merge to main | Orchestrator | pending | All gates PASS |
