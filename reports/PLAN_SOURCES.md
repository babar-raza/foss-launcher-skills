# Plan Sources

## PrimaryPlanSource
- **Path**: `C:\Users\prora\.claude\plans\wild-yawning-sprout.md`
- **Type**: Chat-derived production-readiness audit plan (approved by user 2026-03-31)
- **Rationale**: 10 production-grade fixes, 8 minimum-ship requirements, 13 major gaps with root
  causes, complete operator test matrix. Meets SUBSTANTIAL threshold (>=5 steps, acceptance
  criteria, evidence commands).

## ChatExtractedSteps

### Phase 0 — Quick Wins (Fix 7, Fix 10, Fix 5a)
1. Update AGENTS.md §6: add Phase 1.5 (evidence-materialize→mental-model→evidence-decide) to launch chain
2. Update AGENTS.md §12: add evidence-materialize (S-44), mental-model (S-45), evidence-decide (S-43) to skill map; fix S-40 numbering collision
3. Remove `--no-evidence` flag from `scripts/pipeline/audit.py`
4. Update `skills/content-check.md` evidence citation checks from HTML comments to frontmatter `evidence:` block
5. Update `skills/evidence-materialize.md` id from S-40 → S-44; `skills/mental-model.md` id from S-41 → S-45

### Phase 1 — Foundation (Fix 6, Fix 3, Fix 5b)
6. Write `QUICKSTART.md` operator guide (prerequisites, install, first run, verify)
7. Document audit.py vs content_eval relationship in AGENTS.md §12 and README.md
8. Fix `scripts/pipeline/audit.py` per-file fail count to include evidence findings

### Phase 1 (continued)
9. Update README.md skill catalog to add 3 evidence skills (S-43, S-44, S-45)

### Phase 2 — Enforcement (Fix 1, Fix 8, Fix 9) — FUTURE
10. Implement `scripts/path_guard.py` with tests
11. Implement `scripts/check_setup.py` with tests
12. Implement append-only `reports/ops.log`

### Phase 3 — Hardening (Fix 2, Fix 4) — FUTURE
13. Implement `scripts/pre_write.py` mandatory audit hook
14. Write `tests/test_e2e_pipeline.py` integration test using existing fixtures

## ChatExtractedGapsAndFixes
- **G-F1**: S-01 path-guard has no script implementation → Phase 2 Fix 1
- **G-F2**: S-23 ground-check not automatically called in content-writing skills → Phase 3 Fix 2
- **G-Q1**: No end-to-end integration test → Phase 3 Fix 4
- **G-D1**: Evidence citation format contradiction (HTML comments vs frontmatter) → Fix 5a (Phase 0)
- **G-D2**: AGENTS.md §12 skill map missing 3 evidence skills → Fix 7 (Phase 0)
- **G-D3**: AGENTS.md §6 missing Phase 1.5 in launch chain → Fix 7 (Phase 0)
- **G-D4**: README.md quickstart incomplete → Fix 6 (Phase 1)
- **G-A1**: Two parallel validation systems undocumented → Fix 3 (Phase 1)
- **G-Q4**: `--no-evidence` flag in audit.py → Fix 10 (Phase 0)
- **G-U1**: Skill numbering collision (two S-40) → Fix 7 (Phase 0)

## ChatMentionedFiles
- `AGENTS.md` (update §6, §12)
- `skills/content-check.md` (fix evidence checks)
- `skills/evidence-materialize.md` (renumber to S-44)
- `skills/mental-model.md` (renumber to S-45)
- `scripts/pipeline/audit.py` (remove --no-evidence, fix per-file fail count)
- `scripts/pipeline/knowledge_core.py` (verify evidence already has claim_id validation ✓)
- `QUICKSTART.md` (create)
- `README.md` (update skill catalog + validation system docs)

## SubstantialityCheck
SUBSTANTIAL: 10 concrete fixes, 8 minimum-ship requirements, 13 gap categories, acceptance criteria ✓

## ResolutionStrategy
Execute Phase 0 quick wins first (no architecture change), then Phase 1 foundation, then Phase 2+3 in future sprint.

## SecondarySources
- `C:\Users\prora\.claude\plans\floating-imagining-bunny.md` — prior migration plan (completed)
- `AGENTS.md` (repo governance, read-first)
- `README.md` (project documentation)
- `reports/STATUS.md` (self-assessment with G-4/G-5/G-6 deferred gates)

## MissingCandidates
- `scripts/path_guard.py` — needs to be created (Phase 2)
- `scripts/check_setup.py` — needs to be created (Phase 2)
- `tests/test_e2e_pipeline.py` — needs to be created (Phase 3)
