# TC-14: Platform-Capabilities Checker Bug Fix

**Mission:** MT069-2026-09-16-GHA-MINUTES-REARCHITECTURE
**Date:** 2026-09-17

## What was wrong

`scripts/ci/checks/check_platform_capabilities.py::check_example_verification()`
(added 2026-09-06, commit `acd165e07e`) compared the full, real
`registry.PLATFORM_CONTRACT` (7 platforms, never fixture-mocked) against the
caller's narrower `platforms` parameter (`checkable_platforms` — the
declared-AND-active intersection computed in `check_all()`) instead of against
everything the tested `platform_capabilities.yaml` actually declares. A
pre-existing negative-control test, `test_same_fixture_passes_once_the_value_is_corrected`
(dated 2026-08-29, 8 days before the buggy function existed), used a
single-platform fixture that tripped this bug on every run — not real data
drift; the real `platform_capabilities.yaml` was fully in sync with
`registry.PLATFORM_CONTRACT` the whole time.

## What changed

- `scripts/ci/checks/check_platform_capabilities.py`: the reverse-completeness
  loop now checks `platform not in caps["platforms"]` (the tested YAML's own
  full declared set) instead of `platform not in platforms` (the narrower
  parameter).
- `scripts/ci/tests/test_check_platform_capabilities.py`:
  - `test_same_fixture_passes_once_the_value_is_corrected` rescoped to assert
    no `class_kinds` mismatch for `typescript` specifically (its actual
    intent), rather than a blanket `findings == []` that the single-platform
    fixture could never satisfy once the completeness check existed.
  - New test `test_completeness_check_uses_declared_platforms_not_active_subset`
    pins the corrected behavior: a fixture declaring all 7 real platforms but
    marking only 2 as "active" must produce zero completeness findings — the
    exact shape that silently broke before this fix.

## Validation performed

- `pytest scripts/ci/tests/test_check_platform_capabilities.py -v` — 12/12
  passed (9 pre-existing + 1 rescoped + 1 new + the rest unchanged).
- **Correction (TC-11 independent review, 2026-09-17)**: this document
  originally claimed "the full 1594-test governance suite" passed. That number
  is wrong for this scope — `pytest scripts/ci/tests/ --collect-only -q`
  reports **1,112 tests collected** at the time this fix landed (1,114 after
  `TC-15`'s same-day follow-up added 2 more). 1,594 is a different, larger
  scope: `scripts/ci/tests/` plus the additional `scripts/pipeline` tests that
  `skill-governance.yml`'s own CI step runs in the same job — the two numbers
  were conflated when this was first written, not evidence of two
  contradictory facts. `pytest scripts/ci/tests/` (the correct, 1,112/1,114-
  test scope) was re-run after this correction — see `TC-15`'s evidence doc
  for the recorded result, since both fixes were validated together in the
  same run.

## Governed-path handling

Executed under S-115 (`/workflow-harden`) skill context, scope `scripts/ci/**`
— both files this taskcard touched fall within that skill's declared scope,
consistent with the plan's routing decision (no ad hoc edit).

## Not done / deferred

A full audit of this repo's ~40+ other CI check scripts for similar latent
comparison bugs was explicitly out of scope for this taskcard (see the
governing plan's "Tradeoffs, risks, and honest limits" for `TC-14`/`TC-15`) —
this fix closes the one instance found via `TC-05`'s cost-motivated failure
investigation, not a claim of full coverage.
