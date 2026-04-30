# PR-Path Proof Harness

Synthetic test scenarios for CI workflow behavior verification.

Each directory contains a scenario with known expected outcomes.
Run via `scripts/ci/hooks/run_proof_harness.sh`.

## Scenarios

| Directory | Expected CI outcome | Tests |
|-----------|--------------------|----|
| `known-good/` | PASS | All checks pass; valid grade, valid Skills invoked |
| `known-bad-no-skills/` | FAIL | Skills invoked field missing from content commit |
| `known-bad-forbidden-path/` | FAIL | Forbidden path change without override token |
| `known-bad-grade-downgrade/` | FAIL | Grade downgrade from A to F |

## Evidence

Harness run results are captured in `reports/proof-bundles/ci-harness-YYYY-MM-DD.json`.
