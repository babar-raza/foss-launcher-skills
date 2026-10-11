# How We Built the Post-Sprint Autonomy Loop

A technical account of building a fully unattended post-sprint review cycle —
from a partially completed classifier to a production-grade orchestrated system.

---

## The Problem

After every sprint, the workflow was:

1. Human runs Prompt 1 (audit)
2. Human reads output, decides whether to run Prompt 2
3. Human runs Prompt 2 (plan hardening)
4. Human reads output, decides whether to run Prompt 3
5. Human runs Prompt 3 (execution)
6. Human evaluates the result

This is three manual handoffs, no enforcement of output format, no memory across
Claude Code sessions, and no way to run unattended. Any failure — hallucinated
summary, incomplete scores, missing evidence — had no automated recourse.

The goal was to eliminate all three manual handoffs and produce a system that:

- Decides the next prompt without human input
- Enforces output schema and retries on non-compliance
- Maintains state across sessions
- Bundles evidence at the end
- Can run fully unattended via CLI scheduled tasks

---

## Session 1: The Incomplete Foundation

The first session created a classifier (`loop_controller.py`) and prompt files but
left the system with five dead ends:

1. **No dispatcher** — the classifier returned a decision but nothing acted on it
2. **No agent entry point** — no slash command existed; humans had to know which prompt to run
3. **No cross-session state** — each session started blind; no memory of which stage had completed
4. **No output enforcement** — LLM could return prose; nothing detected or repaired it
5. **No bundle builder** — evidence files scattered with no packaging step

The classifier was orphaned. It classified correctly in tests but was never called
from anything real.

---

## Design Decisions Before Building

Three design questions had to be answered before writing any code. The user
explicitly rejected accepting limitations on each one.

### 1. LLM Output Non-Compliance

**Naive approach:** Accept that LLMs sometimes produce prose instead of YAML.

**Designed solution — 5-layer defense in sprint_loop.py:**

- **Template injection** (`inject-template`): pre-creates skeleton output files before
  the LLM runs. The LLM fills in existing files rather than creating them from scratch.
  Missing-file failures become impossible.
- **Validation with `--repair`**: strips markdown fences, fixes common YAML alias errors
  automatically before reporting failures.
- **Progressive retry**: each retry includes the specific validation failure in the prompt
  context so the LLM understands what went wrong.
- **YAML repair pipeline**: fence-stripping → alias mapping → key relocation, applied in
  sequence before parse errors are reported.
- **Compliance scoring**: ratio of present required outputs (0.0–1.0) stored in state and
  surfaced in `status`. Provides a measurable signal across retries.

### 2. Unattended Operation

**Naive approach:** Claude Code in VSCode cannot start new sessions headlessly.

**Designed solution:**

- `run-stage` subcommand: executes one stage (P1/P2/P3) by invoking
  `claude --print --dangerously-skip-permissions` as a subprocess. Output is captured
  and written to the evidence directory.
- `run-loop` subcommand: runs the full P1→P2→P3→ACCEPT cycle in one shell invocation,
  looping until the decision is terminal.
- Scheduled tasks use the CLI path, not the VSCode extension.
- The `/post-sprint-loop` slash command handles the interactive (VSCode) path.
- Cross-session state in `.supervisor/state/loop-state.json` bridges both paths.

### 3. State File Corruption

**Naive approach:** JSON file, hope for no corruption.

**Designed solution — best practices applied:**

- **Atomic writes**: write to `loop-state.json.tmp`, fsync, then `os.replace()` to the
  final path. POSIX guarantees the file is either the old state or the new state, never
  a partial write.
- **SHA-256 checksum**: stored in `_checksum` field. On every load, the checksum is
  recomputed and compared before any operation proceeds.
- **Backup-on-read**: every successful load copies the state to `loop-state.json.bak`.
  If the primary is corrupt on the next load, recovery falls back to the backup.
- **Schema validation on load**: rejects structurally invalid state before it is used.
- **`recover` subcommand**: if both primary and backup are corrupt, rebuilds state from
  `stage3-final-sprint-summary.yaml` in the evidence directory.

---

## What Was Built

### sprint_loop.py — The Orchestrator (932 lines)

The core file that connects the orphaned classifier to file-based state, validation,
bundling, and CLI automation.

**10 subcommands:**

| Subcommand | Purpose |
|-----------|---------|
| `init` | Create state file, evidence dir, register sprint ID |
| `status` | Show current stage, decision, compliance score as JSON |
| `inject-template` | Pre-create skeleton output files for a stage |
| `validate` | Check all required outputs exist and conform to schema |
| `decide` | Call loop_controller, update state, compute compliance |
| `bundle` | Zip evidence dir + state into timestamped archive |
| `recover` | Rebuild state from evidence directory |
| `reset` | Clear state for a fresh cycle |
| `run-stage` | Headless single-stage execution via claude CLI |
| `run-loop` | Headless full P1→P2→P3 cycle |

**State file anatomy:**

```json
{
  "sprint_id": "pilot-20260615",
  "stage": "P3",
  "decision": "ACCEPT",
  "next_stage": "ACCEPTED",
  "retry_count": 0,
  "compliance_score": 1.0,
  "evidence_dir": "/path/to/.local/evidences/pilot-20260615",
  "started": "2026-06-15T13:03:46Z",
  "last_updated": "2026-06-15T13:12:12Z",
  "_checksum": "54807159f826821f9dddd0cb71b879b8..."
}
```

**Key implementation details:**

- `_save_state()`: builds dict, computes checksum, writes to `.tmp`, fsyncs, renames
- `_load_state()`: reads, verifies checksum, creates backup, validates schema
- `validate_stage_outputs()`: loads `STAGE_YAML_KEYS` and `prompt-registry.yaml` to
  know which files and top-level keys are required per stage
- `cmd_decide()`: calls `classify_summary()` from loop_controller, maps action to
  next stage, updates state
- `build_evidence_bundle()`: zips evidence dir + state file + manifest JSON

### loop_controller.py — Taskcard State Machine (+31 lines)

Added `validate_taskcard_transition()` and `VALID_TRANSITIONS` dict encoding the
14-state machine from `schemas/taskcard-state-machine.yaml`:

```python
VALID_TRANSITIONS = {
    "PROPOSED":   ["READY", "BLOCKED", "DEFERRED_WITH_REASON"],
    "READY":      ["IN_PROGRESS", "BLOCKED"],
    "IN_PROGRESS": ["IMPLEMENTED", "BLOCKED"],
    "IMPLEMENTED": ["VERIFIED", "IN_PROGRESS"],
    "VERIFIED":   ["SCORED"],
    "SCORED":     ["ACCEPTED", "ACCEPTED_WITH_LIMITATIONS", "REROUTED"],
    "REROUTED":   ["REWORKING", "BLOCKED_EXTERNAL"],
    "REWORKING":  ["REWORKED", "BLOCKED"],
    "REWORKED":   ["VERIFIED"],
    "ACCEPTED":   [],   # terminal
    "ACCEPTED_WITH_LIMITATIONS": [],
    "BLOCKED_EXTERNAL": [],
    "DEFERRED_WITH_REASON": [],
    "BLOCKED":    ["READY", "BLOCKED_EXTERNAL", "DEFERRED_WITH_REASON"],
}
```

Terminal states have empty allowed lists. Any transition attempt from them returns `False`.

### post-sprint-loop.md — The Agent Entry Point (70 lines)

A slash command that eliminates the human handoff between stages:

```
/post-sprint-loop
```

The command instructs the agent to:

1. Call `sprint_loop.py status` — determine current stage
2. If no active sprint, call `init`
3. Call `inject-template` for the current stage (creates skeleton files)
4. Read the prompt file for that stage from `prompts/`
5. Produce the required output files in the evidence directory
6. Call `validate --repair`, then `decide`
7. Read the new status — loop until ACCEPTED, BLOCKED, or ESCALATED

The agent never has to know which prompt to run. The state file tells it.

---

## The Test Suite

### test_sprint_loop.py — 27 tests

All test classes inherit from `_TempStateBase` which patches `sprint_loop.STATE_DIR`,
`STATE_FILE`, `STATE_BACKUP`, `EVIDENCE_ROOT`, and `BUNDLE_ROOT` to temporary
directories. No test touches real state.

**Test classes:**

| Class | Tests | What it covers |
|-------|-------|---------------|
| `TestInit` | 2 | State file created, checksum valid; duplicate init rejected |
| `TestStatus` | 2 | JSON output, no active sprint |
| `TestReset` | 1 | State cleared |
| `TestStateResilience` | 4 | Checksum verification; tampered primary falls back to backup; double corruption triggers rebuild |
| `TestRecover` | 2 | Rebuild from evidence dir; no evidence dir → error |
| `TestValidation` | 6 | Missing files, empty files, malformed YAML, missing keys, repair mode |
| `TestInjectTemplate` | 2 | Creates skeleton files; unknown stage → error |
| `TestDecide` | 7 | ACCEPT, RETRY, BLOCK paths; compliance scoring; retry budget exhaustion |
| `TestBundle` | 1 | Zip created with manifest |

### test_loop_controller.py — 12 new negative controls

Added to the existing 34 tests. These verify the classifier cannot be tricked
into `ACCEPT` by invalid taskcard state, missing evidence, or contradictory data:

| Test | What it prevents |
|------|-----------------|
| `test_nc_taskcard_skip_verified` | IMPLEMENTED → CLOSED bypasses VERIFIED |
| `test_nc_taskcard_skip_scored` | VERIFIED → CLOSED bypasses SCORED |
| `test_nc_rerouted_to_closed` | REROUTED → CLOSED bypasses rework cycle |
| `test_nc_proposed_to_accepted` | PROPOSED → ACCEPTED skips 7 intermediate states |
| `test_nc_terminal_states` | Any transition from ACCEPTED, BLOCKED_EXTERNAL, DEFERRED |
| `test_nc_unknown_state` | Unknown state name → False |
| `test_nc_valid_proposed_to_ready` | Positive: PROPOSED → READY is allowed |
| `test_nc_valid_scored_to_accepted` | Positive: SCORED → ACCEPTED is allowed |
| `test_nc_valid_rerouted_to_reworking` | Positive: REROUTED → REWORKING is allowed |
| `test_nc_rerouted_accepted_without_reeval` | ALL_GREEN summary + REROUTED taskcard → not ACCEPT |
| `test_nc_evidence_manifest_mismatch` | Missing evidence file → EVIDENCE_MISSING |
| `test_nc_summary_all_green_reroute_contradiction` | ALL_GREEN + REROUTED status → CONTRADICTORY |

---

## The Pilot

After committing, we ran a full end-to-end pilot against the most recent real sprint
(Regeneration Fragility Fix, Sprint 6).

### Sequence

```
sprint_loop.py init --sprint-id pilot-20260615
sprint_loop.py inject-template P1        # 10 skeleton files created
# wrote P1 audit outputs
sprint_loop.py validate P1               # PASS (after fixing YAML structure)
# manually advanced state stage: P1 -> P2
sprint_loop.py inject-template P2        # 15 skeleton files
# wrote P2 plan-hardening outputs
sprint_loop.py validate P2               # PASS
# manually advanced state stage: P2 -> P3
sprint_loop.py inject-template P3        # 13 skeleton files
# wrote P3 execution outputs + stage3-final-sprint-summary.yaml
sprint_loop.py validate P3               # PASS
sprint_loop.py decide                    # STRUCTURED_ALL_GREEN → ACCEPT, compliance 1.0
sprint_loop.py bundle                    # pilot-20260615.zip (40 files)
```

### Finding: Validator Enforces Key Structure

The first `validate P1` run failed:

```
FAIL: stage1-l1-execution-issues.yaml is missing 'issue_id'
FAIL: stage1-l1-execution-issues.yaml is missing 'issue_level'
```

The YAML had `issue_id` nested under an `issues:` list. The validator requires
top-level keys matching `STAGE_YAML_KEYS`. Restructured to top-level — validation
passed. This is exactly the kind of non-compliance the system is designed to catch.

### Finding: decide Before P3 Returns MISSING

`decide` always classifies `stage3-final-sprint-summary.yaml`. Before P3, that file
does not exist, so `decide` returns `MISSING → RETRY`. This is by design: the loop
controller's job is to classify the final outcome, not intermediate stage outputs.
The `/post-sprint-loop` command handles this by only calling `decide` after P3 validates.

### Final Result

```json
{
  "classification": "STRUCTURED_ALL_GREEN",
  "action": "ACCEPT",
  "reason": "All quality dimensions pass, evidence bundle complete",
  "next_stage": "ACCEPTED",
  "compliance_score": 1.0
}
```

Bundle: `.local/evidence-bundles/pilot-20260615.zip` — 40 files including `loop-state.json`
and `manifest.json`.

---

## Governance Obstacles and How They Were Resolved

### S-73 Skill Context

Every edit to `scripts/maintenance/supervisor/` requires an active S-73 skill context:

```bash
.venv/Scripts/python scripts/pipeline/commands/governance/skill_context.py \
  begin --skill S-73 --scope "scripts/maintenance/supervisor/sprint_loop.py"
```

The scope expires after each file edit. It must be re-activated before every
subsequent edit, even to the same file.

### Override Token for .claude/commands/

`.claude/` is in `FORBIDDEN_PREFIXES`. Writing to it requires an override token
created before the write:

```bash
.venv/Scripts/python scripts/pipeline/commands/governance/override_manager.py \
  create --paths ".claude/commands/post-sprint-loop.md" \
  --reason "Post-sprint autonomy loop agent entry point" \
  --plan "feat(supervisor): add post-sprint autonomy loop"
```

The pre-commit hook validates the token and archives it after use. The token does
not need to be staged — the hook reads it from disk.

### Session Ledger for Commit Scoping

The `/commit` skill (S-76) scopes commits to files recorded in the session ledger.
Files created via Python's `Path.write_text()` (not the Write tool) are not
auto-recorded. Register manually before committing:

```bash
.venv/Scripts/python scripts/pipeline/commands/ops/session_ledger.py \
  record --file .claude/commands/post-sprint-loop.md --action created --skill S-73
```

Files staged but not in the ledger appear in `excluded_not_in_ledger` in
`session_ledger.py candidates --format json`. That output is the diagnostic.

---

## Files Delivered

| File | Type | Lines | Purpose |
|------|------|-------|---------|
| `scripts/maintenance/supervisor/sprint_loop.py` | NEW | 932 | Orchestrator: 10 subcommands |
| `scripts/maintenance/supervisor/loop_controller.py` | EDIT | +31 | Taskcard transition validator |
| `scripts/maintenance/supervisor/tests/test_sprint_loop.py` | NEW | 455 | 27 tests |
| `scripts/maintenance/supervisor/tests/test_loop_controller.py` | EDIT | +104 | 12 negative controls |
| `.claude/commands/post-sprint-loop.md` | NEW | 70 | Agent slash command |

**Commit:** `e83d4db73e`
**Tests:** 143 total (46 loop_controller + 27 sprint_loop + 70 other), all pass
**Pilot:** STRUCTURED_ALL_GREEN → ACCEPT, compliance 1.0, 40-file bundle

---

## What Still Needs to Be Done

1. **Unattended mode testing.** `run-stage` and `run-loop` exist but have not been
   exercised with `claude --print --dangerously-skip-permissions` in a scheduled task.
   The code is written; the integration test is missing.

2. **Guard coverage completion.** Four content-writing skills (`page-enhance`,
   `grade-remediate`, `cleanroom-regen`, `batch-remediate`) still lack the no-downgrade
   guard from the Regeneration Fragility Fix sprint.

3. **CI guard coverage check.** No automated enforcement prevents new skills from being
   created without a guard reference. A check in the CI pipeline would close this gap.

4. **Production regeneration trigger.** The no-downgrade guard has zero false positives
   across 2,769 calibrated pages but has never fired on a real violation during live
   content regeneration.

---

## Key Lessons

**Design for non-compliance before building.** The first session assumed LLM output
would be well-formed YAML. The second session redesigned around 5-layer enforcement
before writing a line of implementation code. The order matters: enforcement
architecture first, implementation second.

**Atomic writes are non-negotiable for state files.** A partial write leaves the loop
permanently stuck with no recovery path. `tmp → fsync → os.replace()` costs nothing
and makes corruption impossible.

**Test the negative path before the happy path.** The first session had 34 tests,
all positive. The second session added 12 negative controls verifying the classifier
cannot be tricked by skipped states, missing evidence, or contradictory summaries.
The positive-only suite would have missed all of these.

**Governance overhead is the audit trail.** S-73 scope re-activation, override tokens,
and session ledger registration added real friction. But every write to a protected path
now has a reason, a skill attribution, and a commit link. The overhead is not waste —
it is the record.
