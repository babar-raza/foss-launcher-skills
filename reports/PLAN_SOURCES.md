# Plan Sources

<!-- Updated 2026-05-14: PRD-005 audit returned NO-SHIP; orchestrator session executing minimum-bar fixes -->

## Session 2026-05-14 (PRD-006/007/008 execution)

### ChatExtractedSteps
Audit response identified 8 minimum-ship items (S1–S8) and 5 categories of fixes (F, D, U, RC, A).
Orchestrator mode activated; autonomous execution of fixes.

### ChatExtractedGapsAndFixes
- S1: `getting-started.md` references `requirements.txt` (does not exist; real file: `scripts/requirements.txt`)
- S2: `launch-product.md` Phase 1.5 steps reference S-40/S-41 instead of correct S-44/S-45
- S3: `RUNBOOK.md` documents wrong paths for override_manager, session_ledger, skill_run_manager
- S4: S-23 registry points to `scripts/pipeline/audit.py` shim confirmed broken; redirect to real audit
- S5: 4 failing tests (audit shim, readme_sync missing entry)
- S6: `data/products.json` missing (referenced by refresh_knowledge.py auto-clone path)
- S7: `PIPELINE.md` documents flat structure no longer matching `scripts/pipeline/commands/*/`
- S8: Translation skills (S-99, S-100, S-107) documented as non-functional; need registry note or documentation

### ChatMentionedFiles
- `skills/getting-started.md`, `skills/launch-product.md`, `docs/RUNBOOK.md`, `docs/PIPELINE.md`
- `skills/registry.yaml`, `scripts/pipeline/audit.py`, `scripts/pipeline/commands/content/audit.py`
- `data/products.json` (missing), `scripts/pipeline/commands/knowledge/refresh_knowledge.py`
- `skills/translate-batch.md`, `skills/translate-page.md`, `skills/translate.md`
- `reports/STATUS.md`, `reports/CHANGELOG.md`, `TASK_BACKLOG.md`

### SubstantialityCheck
SUBSTANTIAL: 8 minimum-ship requirements + 13 gap categories + evidence commands inferred from audit.

### ResolutionStrategy
Chat is PRIMARY for this session. Existing disk plan `plans/from_chat/20260514_155101_from_chat_production_readiness_remediation.md` covers the same remediation mission. No new plan file needed; update PLAN_INDEX.md with execution status.

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
---

## Orchestrator Protocol Extraction - 2026-05-14 15:51

## PrimaryPlanSource
- **Path**: `plans/from_chat/20260514_155101_from_chat_production_readiness_remediation.md`
- **Type**: Chat-derived production-readiness remediation plan
- **Rationale**: The latest user request explicitly directs autonomous end-to-end execution using specialist agents, a live TODO list, evidence artifacts, self-review gates, and final pilots. The immediately preceding audit report supplies the concrete gaps and recommended execution order.

## ChatExtractedSteps
1. Resolve plan sources from chat first, then disk.
2. Update `reports/PLAN_SOURCES.md` with extracted steps, gaps, files, substantiality, strategy, and evidence commands.
3. Create a chat-derived primary plan under `plans/from_chat/`.
4. Append the primary plan to `reports/PLAN_INDEX.md`.
5. Harden the plan so it has steps, acceptance criteria, and evidence commands.
6. Build or update `TASK_BACKLOG.md` from plan sources, docs, TODOs, failing tests, and CI notes.
7. Split the work into at most five parallel workstreams.
8. Create per-agent workspaces under `reports/agents/<agent>/<task_id>/`.
9. Spawn specialist agents for discovery, implementation, tests, docs, and ops.
10. Require every agent to produce plan, changes, evidence, commands, and self-review files.
11. Route any self-review dimension below 4/5 to hardening tickets.
12. Merge only after tests are green, docs are updated, and evidence is present.
13. Run pilots to verify the end-to-end pipeline and capture evidence.

## ChatExtractedGapsAndFixes
- Installer embedded mode copies only root `scripts/*.py`; fix by copying required package trees or making standalone the only supported mode.
- `tools/distribute.py` exposes internal skills to Claude commands; fix by sharing registry-aware filtering with `sync_commands.py`.
- `site_planner.py` path points to an org scanner rather than a launch planner; fix or rewire site-planning entrypoint.
- `refresh_knowledge.py` calls moved nonexistent `scripts/pipeline/scout.py` and `scripts/pipeline/merge.py`; fix to canonical wrappers or command modules.
- S-23 `ground-check` registry points to semantic content audit rather than the evidence-enforcing gate; fix audit naming/bindings and fail-closed behavior.
- Docs and skills mention nonexistent script paths; add validation and update stale references.
- `pyproject.toml` console script `foss-audit` points to missing `scripts.audit`.
- Scout dependencies are missing and scout tests are skipped; make release readiness fail when core dependencies are absent.

## ChatMentionedFiles
- `reports/PLAN_SOURCES.md`
- `reports/PLAN_INDEX.md`
- `TASK_BACKLOG.md`
- `reports/agents/<agent_name>/<task_id>/plan.md`
- `reports/agents/<agent_name>/<task_id>/changes.md`
- `reports/agents/<agent_name>/<task_id>/evidence.md`
- `reports/agents/<agent_name>/<task_id>/self_review.md`
- `reports/agents/<agent_name>/<task_id>/commands.sh`
- `reports/HARDENING_TICKETS/<task_id>.md`
- `reports/STATUS.md`
- `reports/CHANGELOG.md`
- `install.sh`
- `install.ps1`
- `tools/distribute.py`
- `scripts/sync_commands.py`
- `scripts/pipeline/commands/launch/site_planner.py`
- `scripts/pipeline/commands/knowledge/refresh_knowledge.py`
- `skills/registry.yaml`
- `skills/new-docs-page.md`
- `pyproject.toml`

## SubstantialityCheck
SUBSTANTIAL: the chat and preceding audit contain more than 5 actionable steps, more than 3 concrete gaps with fixes, explicit acceptance criteria, and evidence commands.

## ResolutionStrategy
Use the chat-derived remediation plan as the primary source. Execute in five workstreams: discovery/architecture, implementation, tests, docs, and ops/readiness. Use small increments, run tests after each integrated change, write evidence artifacts, and harden any workstream with self-review scores below 4/5.

## SecondarySources
- `reports/skill-gaps/2026-05-14-production-readiness-audit.md`
- Previous assistant audit report in chat
- `AGENTS.md`
- `README.md`
- `QUICKSTART.md`
- `OPERATOR_GUIDE.md`
- `docs/RUNBOOK.md`
- `skills/registry.yaml`

## MissingCandidates
- None for the primary plan. Missing script paths will be tracked as remediation tasks.

---

## Session 2026-05-15 (Parity Migration Verification Program)

### ChatExtractedSteps
8-phase parity program: Phase 1 recon (COMPLETE) → Phase 2 aspose.org inventory → Phase 3 foss-launcher inventory → Phase 4 parity analysis → Phase 5 target architecture → Phase 6 taskcard decomposition → Phase 7 implementation → Phase 8 verification.

### ChatExtractedGapsAndFixes
- 59 CI validation checks missing in foss-launcher (4 vs 63)
- docs/governance/ and docs/workflows/ absent (22 docs in aspose.org)
- scripts/pipeline/lib/ shared library layer absent (19 modules)
- scripts/pipeline/core/ foundation modules absent
- gap-eval profiles incomplete (sample only vs 7 families)
- GRADE_CONTRACT.md absent
- blog-migrate and pipeline-harden skills absent
- .env.example absent
- 77 shared skills with unverified content parity (diverged file sizes)

### ChatMentionedFiles
- `C:\Users\prora\.claude\plans\bright-singing-harbor.md` (primary plan)
- `reports/parity/aspose-inventory.yaml` (Phase 2 output)
- `reports/parity/foss-inventory.yaml` (Phase 3 output)
- `reports/parity/parity-matrix.md` (Phase 4 output)
- `reports/parity/gap-report.md` (Phase 4 output)
- `reports/parity/target-architecture.md` (Phase 5 output)
- `reports/parity/taskcards/TC-INDEX.md` (Phase 6 output)
- `reports/parity/verification-evidence.md` (Phase 8 output)
- `reports/parity/closure-report.md` (Phase 8 output)

### SubstantialityCheck
SUBSTANTIAL: 8-phase plan with goals, inputs, outputs, exit criteria per phase, 8-layer verification method, parity status vocabulary, gap classification vocabulary, inventory schema, ~27 numbered steps.

### ResolutionStrategy
`plans/from_chat/20260515_120000_from_chat_parity_migration_verification.md` is the PRIMARY plan for this session. bright-singing-harbor.md is the reconnaissance backing document. Execution begins at Phase 2.

## PrimaryPlanSource (2026-05-15)
- **Path**: `plans/from_chat/20260515_120000_from_chat_parity_migration_verification.md`
- **Type**: Chat-derived parity migration and verification program
- **Rationale**: Comprehensive 8-phase plan with full inventory schema, parity vocabulary, gap classification vocabulary, 27 numbered steps, acceptance criteria, and evidence commands. Phase 1 reconnaissance already complete in bright-singing-harbor.md.

## SecondarySources (2026-05-15)
- `C:\Users\prora\.claude\plans\bright-singing-harbor.md` — Phase 1 reconnaissance findings (repo maps, skill comparison, ID divergence analysis)
- `D:\onedrive\Documents\GitHub\aspose.org\AGENTS.md` — reference governance (read-only)
- `C:\Users\prora\OneDrive\Documents\GitHub\foss-launcher-skills-gitlab\AGENTS.md` — target governance
