<!-- Adapted from aspose.org docs/workflows/ for standalone use -->

# Capability Classification and Gap Escalation

Before starting any task that is not a direct invocation of a single registered skill, the agent must classify its capability level and act accordingly.

### Capability states (choose exactly one)

| State | Definition | Required action |
|-------|-----------|----------------|
| **FULL** | Every step of the requirement is covered by a registered skill | Invoke the skill chain; no gap report needed |
| **PARTIAL** | Some steps are covered; others are not | Execute skill-covered steps; produce gap escalation report for uncovered steps; do not perform uncovered steps through ad hoc work |
| **NONE** | No registered skill covers this requirement | Do not start work; produce gap escalation report immediately; await human decision |
| **BROKEN** | A required skill exists but fails when invoked | Invoke it, capture failure output; produce breakage report; do not bypass; await human decision |

### Classification output

When starting a novel, multi-part, or ambiguous request, state:

```
CAPABILITY ASSESSMENT -- {brief task description}
State: FULL | PARTIAL | NONE | BROKEN
Skill(s) covering this task: [list skill IDs and names, or "none"]
Gap (if PARTIAL or NONE): [describe what is not covered]
Broken skill (if BROKEN): [skill ID, invocation attempted, error observed]
Planned action: [what you will do next]
```

For requests that are direct invocations of a single skill or a predefined chain, this output is implicit -- you do not need to print it.

### Gap escalation report format

When state is PARTIAL or NONE, produce this report after completing any skill-covered work, and save to `reports/skill-gaps/{YYYY-MM-DD}-{task-slug}.md`:

```
SKILL GAP ESCALATION
Task: {what was requested}
Capability state: PARTIAL | NONE
Skills invoked (completed): [list]
Uncovered requirement: {precise description}
Impact: {what the user will not get until this gap is filled}

ENHANCEMENT PLAN
  Title: {short name for the missing skill}
  Proposed skill ID: {next available S-xx or descriptive name}
  Input: {what the skill would receive}
  Output: {what the skill would produce}
  Skill file location: skills/{proposed-name}.md
  Depends on: {upstream skills it would call}
  Estimated complexity: LOW | MEDIUM | HIGH
  Workaround available: YES | NO
  If YES -- workaround description: {only if it can be done safely without fabrication}
```

### Broken skill report format

When state is BROKEN, save to `reports/skill-breakage/{YYYY-MM-DD}-{skill-id}.md`:

```
SKILL BREAKAGE REPORT
Skill: {ID and name}
Invocation: {exact command or invocation attempted}
Expected output: {what the skill spec says it should produce}
Actual output / error: {verbatim failure output}
Impact: {what tasks are blocked until this is fixed}
Suggested diagnosis: {most likely cause based on the error}
```

### Novel requirement protocol

If the requirement does not match any known task type:

1. Classify capability (FULL / PARTIAL / NONE) -- for truly novel requirements this will
   usually be PARTIAL or NONE.
2. If PARTIAL: execute skill-covered steps, then produce gap escalation report.
3. If NONE: produce gap escalation report immediately. Do not attempt the work.
4. Do not design a new workflow and execute it inline -- this is prohibited.
5. Fill in the "Enhancement Plan" section of the gap escalation report fully. This is the
   mechanism by which the skill system grows to cover new requirements.

### Anti-workaround mandate

Before creating any new script file anywhere in the repository, or before writing any
inline loop, shell hack, or ad hoc code in bash to work around a missing pipeline step,
you MUST:

1. **Check for an existing script** -- look in `scripts/pipeline/` for a script that covers
   the need. If one exists but is broken or incomplete, classify as BROKEN and file a
   breakage report. Fix the script; do not invent a parallel workaround.
2. **Check for an existing skill** -- if the task maps to a registered skill, invoke it.
   If the skill fails, classify as BROKEN. Do not bypass with ad hoc code.
3. **If the capability is truly absent** -- classify as NONE, produce a gap escalation report
   immediately, and add the missing script or skill in the correct layer with CONTRACT comment,
   tests, and docs before using it. Do not execute ad hoc work pending the addition.
4. **If a workaround is unavoidable** -- mark it explicitly as TEMPORARY in a comment, create
   a tracked remediation item (gap escalation report at `reports/skill-gaps/`), and include
   the exit criteria for when the workaround becomes unnecessary.
5. **Reverify after every fix** -- after adding or repairing a capability, re-run the original
   failing scenario to prove the workaround is no longer needed. The sprint is not complete
   until every former ad hoc step is replaced by its durable system path.

### Defect classification during validation

When a validation run (pilot rerun, E2E evaluation, benchmark) surfaces an error or crash,
classify it **before** routing. Apply this decision tree:

```
1. Does the failing code path exist in any file modified by the current track?
   YES -> Track regression. Block closure until fixed.
   NO  -> Go to step 2.

2. Does git blame show the failing line was introduced by a track commit?
   YES -> Track regression (latent, activated by new conditions).
   NO  -> Go to step 3.

3. Is the error triggered by test data/fixtures created by the track?
   YES -> Track test design issue. Fix fixture, re-validate.
   NO  -> Pre-existing defect. Route to owner track (standalone item
         or appropriate backlog track). Do NOT block current track closure.
```

Record the classification in this format (inline or in a report):

```
DEFECT CLASSIFICATION
  Error: {type} at {file}:{line}
  Triggering page: {path}
  Classification: regression | latent-regression | test-design | pre-existing
  Evidence: {git blame hash + date, file inventory check}
  Routed to: {item ID or "current track"}
  Blocks closure: yes | no
```

Pre-existing defects never contaminate the validating track's closure decision.
