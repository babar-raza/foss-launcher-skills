# Plan Sources

## PrimaryPlanSource
- **Path**: `C:\Users\prora\.claude\plans\reactive-sprouting-matsumoto.md`
- **Type**: Quarterly-review score-improvement master plan (chat-derived, 2026-04-21)
- **Rationale**: 12 taskcards, 8 gap categories, phased roadmap, acceptance criteria, evidence
  commands, governance rules. SUBSTANTIAL (>5 steps, acceptance criteria, evidence commands).

## ChatExtractedSteps

### Phase 0 — Immediate (Close the Confidence Gap)
1. Fix scout `requires_tree_sitter` skip guard to also check `tree_sitter_language_pack`
2. Add adversarial path-guard tests (TASK-01) — already exists in test_path_guard.py ✓
3. Add no_downgrade_guard fallback tests (TASK-02) — already exists in test_no_downgrade_guard.py ✓
4. Extend config schema negative tests (TASK-03) — governance.roles, session_limits type errors
5. Add evidence pipeline failure-mode tests (TASK-04) — materialize/verify with missing inputs
6. Add pre_write stale-model block test (TASK-05) — stale_since != null → FAIL
7. Create TASK_BACKLOG.md from all plan sources
8. Create agent workspace directories for all Phase 0 tasks

### Phase 1 — Near-term (Delivery Evidence + CI Proof)
9. Enable CI workflow and commit .github/ untracked files
10. Make skill-provenance CI check blocking (GW-1, GB-4)
11. Build scripts/quarterly_readiness.py (GW-4)

### Phase 2 — Medium-term (Code Structure)
12. Add pyproject.toml for package boundary (SW-1)
13. Fix hardcoded evidence paths (SW-2)
14. Begin launcher deduplication (GB-3)

## ChatExtractedGapsAndFixes
- **GB-1**: Fallback/degraded evidence paths untested → TASK-04
- **GB-2**: Config schema rejection untested → TASK-03
- **GB-3**: 3,175 duplicate launcher lines → Phase 2
- **GB-4**: Delivery evidence unenforceable → Phase 1
- **GB-5**: 15/17 scout test failures visible in git history → Fix skip guard
- **CR-1**: S-01 path-guard claims untested adversarially → TASK-01 (DONE)
- **CR-2**: no_downgrade_guard fallback untested → TASK-02 (DONE)
- **CR-3**: Evidence pipeline silent failures → TASK-04
- **CR-4**: Commit-msg hook opt-in → Phase 1
- **CR-5**: Schema negative tests missing → TASK-03
- **SW-1**: No pyproject.toml → Phase 2
- **SW-2**: Hardcoded evidence paths → Phase 2
- **GW-4**: No quarterly readiness self-audit → Phase 1

## ChatMentionedFiles
- `tests/test_scout_units.py` (fix requires_tree_sitter guard)
- `tests/test_schema_validate.py` (extend with negative cases)
- `tests/test_materialize.py` (extend with missing-input failure modes)
- `tests/test_verify.py` (extend with malformed PEF failure modes)
- `tests/test_pre_write.py` (extend with stale_since test)
- `reports/PLAN_SOURCES.md` (this file)
- `reports/PLAN_INDEX.md` (update)
- `reports/TASK_BACKLOG.md` (create)
- `reports/agents/` (create workspace dirs)

## SubstantialityCheck
SUBSTANTIAL: 12 taskcards, acceptance criteria, evidence commands ✓

## ResolutionStrategy
Execute Phase 0 immediately (low-risk test additions + skip-guard fix), then Phase 1 (CI/evidence),
then Phase 2 (structural refactor). All changes improve real quality AND reviewer-visible signals.

## CoPrimaryPlanSource (2026-04-21, Parity Program Sprint 2)
- **Path**: `C:\Users\prora\.claude\plans\wondrous-skipping-diffie.md`
- **Type**: Skill parity program — aspose.org → foss-launcher-skills-gitlab (Sprint 1 complete, Sprint 2 in progress)
- **Rationale**: TC-020 (commit blocker) + TC-021 (translator gap blocker) are the active critical path. Sprint 1 delivered 42 skills + infrastructure (84 total) but is entirely uncommitted. SUBSTANTIAL: 5 new taskcards, Sprint 2 exit criteria, evidence commands, guardrails.
- **Active taskcards**: TC-020 (commit), TC-021 (translator gap), TC-022 (CI), TC-023 (hook behavioral), TC-024 (live content)

## SecondarySources
- `C:\Users\prora\.claude\plans\wild-yawning-sprout.md` — prior production-readiness plan (completed)
- `C:\Users\prora\.claude\plans\floating-imagining-bunny.md` — prior migration plan (completed)
- `AGENTS.md` (repo governance)
- `reports/skills-product-audit/migration-plan.md` (7-phase migration plan, Phases 1-6 unstarted)
- `reports/STATUS.md` (self-assessment)

## MissingCandidates
- `pyproject.toml` — needs to be created (Phase 2)
- `scripts/quarterly_readiness.py` — needs to be created (Phase 1)
- `skills/score-readiness.md` — needs to be created (Phase 1)
- `skills/verify-claims.md` — needs to be created (Phase 1)
