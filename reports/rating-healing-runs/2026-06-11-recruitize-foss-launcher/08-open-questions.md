# Phase 08 — Open Questions

**Sprint:** 2026-06-11-recruitize-foss-launcher

---

## Scoring Questions

### OQ-001: What is the actual Recruitize score post-sprint?

All scores in this sprint are estimates based on applying the APRV model to the git-tracked state.
The Recruitize reviewer was not re-run (requires external blog/announcement context not available in this environment).
**Action needed:** Run the actual Recruitize reviewer to get verified A/P/R/S scores.

### OQ-002: Does the reviewer recognize docs/adr/ as R5 evidence?

The reviewer is expected to check for an ADR directory. Whether it scores R5 based on presence of docs/adr/ alone vs. requiring specific ADR format is unclear.
**Action needed:** Inspect the reviewer's ADR detection logic.

### OQ-003: Does CHANGELOG.md format matter for R3?

The CHANGELOG.md uses a Keep a Changelog format with `## [0.1.0]` versioned entries. Whether the reviewer requires semver format, specific headers, or just non-empty file content is unclear.
**Action needed:** Inspect the reviewer's CHANGELOG parsing logic.

### OQ-004: Does the coverage margin of 0.04% cause CI failures?

pytest with `--cov-fail-under=12` fails at 11.96%. The local_gate.py passes (no coverage threshold). This creates inconsistency between local and CI behavior.
**Action needed:** Add tests for new modules (structured_log.py) to push coverage above 12.00%.

---

## Architecture Questions

### OQ-005: Should run_outcome_log.py add actual file locking?

The current approach documents the single-process assumption. If multi-process execution is ever added to the pipeline, file locking will be needed.
**Approach A:** Add `fcntl`/`portalocker` file locking now (more robust, adds dependency)
**Approach B:** Keep single-process assumption documented, add locking if/when needed

### OQ-006: Should structured logging be integrated into existing skill modules?

The structured_log.py module was added as P5 evidence. For it to have full value, it should be used by adaptive_retry.py, run_outcome_log.py, and local_gate.py.
**Action needed:** Evaluate whether to add structured logging calls to existing modules.

---

## Process Questions

### OQ-007: How to prevent "claimed-not-done" failures in future sprints?

RC-008 was claimed done in 73d2fc8 but was not executed. The root cause was writing the ledger before verifying execution.
**Process fix:** Require grep/ls verification command for each claimed fix, run before marking done.
