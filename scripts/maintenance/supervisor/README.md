# Post-Sprint Autonomy Loop (PSAL) — S-103

Machine-controlled post-sprint review cycle. Replaces the manual
Prompt 1 → Prompt 2 → Prompt 3 → inspect → decide loop.

**Skill ID**: S-103 | **Slash command**: `/post-sprint-loop`

## Layout

```
scripts/maintenance/supervisor/
├── loop_controller.py          # Core engine: classify, validate, decide (9 classifications)
├── sprint_loop.py              # Orchestrator: 10 subcommands, state persistence, bundling
├── README.md                   # This file
├── prompts/
│   ├── prompt1-post-sprint-audit.md
│   ├── prompt2-plan-hardening.md
│   ├── prompt3-controlled-execution.md
│   ├── prompt-loop-controller.md
│   ├── prompt-output-contracts.md
│   ├── project-adapter-template.md
│   ├── project-adapter-aspose.yaml
│   └── prompt-registry.yaml
├── schemas/
│   ├── stage1-issue-model-schema.yaml
│   ├── stage2-taskcard-contract.yaml
│   ├── stage3-quality-scoring-rubric.yaml
│   ├── taskcard-state-machine.yaml      # 14-state machine; source of VALID_TRANSITIONS
│   ├── summary-parser-contract.yaml
│   ├── loop-decision-state-machine.yaml
│   ├── evidence-bundle-contract.yaml
│   ├── project-adapter-contract.yaml
│   └── governance-contract.yaml
└── tests/
    ├── test_loop_controller.py  # 46 tests (34 original + 12 negative controls)
    └── test_sprint_loop.py      # 27 tests (state, resilience, validation, decide, bundle)
```

## Quickstart

```bash
# Interactive (Claude Code): run /post-sprint-loop in a session
# The agent reads state, injects templates, runs the correct prompt, validates, decides.

# Headless — single stage:
.venv/Scripts/python scripts/maintenance/supervisor/sprint_loop.py run-stage P1

# Headless — full cycle (P1 → P2 → P3 → ACCEPT):
.venv/Scripts/python scripts/maintenance/supervisor/sprint_loop.py run-loop

# Manual step-by-step:
.venv/Scripts/python scripts/maintenance/supervisor/sprint_loop.py init --sprint-id my-sprint-01
.venv/Scripts/python scripts/maintenance/supervisor/sprint_loop.py inject-template P1
# ... produce P1 outputs in .local/evidences/my-sprint-01/ ...
.venv/Scripts/python scripts/maintenance/supervisor/sprint_loop.py validate P1 --repair
.venv/Scripts/python scripts/maintenance/supervisor/sprint_loop.py decide
.venv/Scripts/python scripts/maintenance/supervisor/sprint_loop.py bundle
```

## sprint_loop.py Subcommands

| Subcommand | Purpose |
|-----------|---------|
| `init` | Create state file, evidence dir, register sprint ID |
| `status` | Show current stage, decision, compliance score as JSON |
| `inject-template` | Pre-create skeleton output files for a stage |
| `validate [--repair]` | Check all required outputs; auto-fix fences and common YAML errors |
| `decide` | Classify final summary, update state, compute compliance score |
| `bundle` | Zip evidence dir + state into `.local/evidence-bundles/<id>.zip` |
| `recover` | Rebuild state from evidence directory if state is corrupt |
| `reset` | Clear state for a fresh cycle |
| `run-stage` | Headless single-stage via `claude --print --dangerously-skip-permissions` |
| `run-loop` | Headless full P1→P2→P3 cycle |

## State File

Location: `.supervisor/state/loop-state.json`

- Atomic writes: `tmp → fsync → os.replace()`
- SHA-256 `_checksum` field verified on every load
- Backup-on-read to `loop-state.json.bak`
- `recover` subcommand rebuilds from evidence if both files corrupt

## Decision Flow

1. Parse `stage3-final-sprint-summary.yaml` from evidence directory
2. Classify into one of 9 states (STRUCTURED_ALL_GREEN, PROSE_ONLY, MISSING, etc.)
3. Validate evidence bundle completeness (`validate_evidence_bundle`)
4. Check quality scores (all dimensions must be ≥ 4/5 — `check_quality_scores`)
5. Emit decision: ACCEPT / RETRY / BLOCK / ESCALATE

Only `STRUCTURED_ALL_GREEN` with complete evidence and passing scores → `ACCEPT`.
Retry budget: max 3 retries before escalating to `BLOCK`.

## Taskcard State Machine

14 states defined in `schemas/taskcard-state-machine.yaml`:

`PROPOSED → READY → IN_PROGRESS → IMPLEMENTED → VERIFIED → SCORED → ACCEPTED`

With branches for BLOCKED, REROUTED, REWORKING, REWORKED, and three terminal states
(ACCEPTED, BLOCKED_EXTERNAL, DEFERRED_WITH_REASON). Enforced by
`validate_taskcard_transition()` in `loop_controller.py`.

## Registration

- Skill ID: **S-103**
- Skills registry: `docs/registries/skills.md` ✓
- Agent command: `.claude/commands/post-sprint-loop.md` ✓
- CLAUDE.md quick reference: Operations table ✓
- Build document: `docs/post-sprint-autonomy-loop-build.md` ✓
- Tests: 73 tests total (46 loop_controller + 27 sprint_loop), all pass ✓
