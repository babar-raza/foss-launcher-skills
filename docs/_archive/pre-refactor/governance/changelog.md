# Archived Document

Archived: 2026-05-30

Reason: Superseded by the docs architecture refactor. This file is retained for history only; do not use it as current operating guidance.

Successor: See docs/README.md for the current documentation map and canonical references.

Original path: docs/_archive/pre-refactor/governance/changelog.md

---

---
# Governance child document — migration ledger
# Source: new (governance refactor tracking)
# Plan: delightful-wondering-hartmanis (TC-03)
# Created: 2026-04-28
---

# Governance Refactor — Migration Ledger

| Date | Commit | Action | Notes |
|------|--------|--------|-------|
| 2026-04-28 | Commit 0A | TC-01: Protected child-doc paths | Added docs/governance/, docs/workflows/, docs/registries/ to FORBIDDEN_PREFIXES |
| 2026-04-28 | Commit 1A | TC-03/04/05: Created 19 child docs | Verbatim extraction from AGENTS.md |
| 2026-04-28 | Commit 2A | TC-06: Dual-read DAR parsers | Prefer child doc, fall back to AGENTS.md |
| 2026-04-28 | Commit 2B | TC-07/08/09: Slim AGENTS.md root | Replaced moved sections with stub+pointer headings |
| 2026-04-28 | Commit 3A | TC-11/12: Collateral updates | Updated CLAUDE.md, CODEX.md, governance.md, skill refs |
| 2026-04-28 | Commit 3B | TC-13/14/15: Guardrails + sync + ledger | CI scripts, mirror sync, this ledger |

## Commit CL — Final Verification + Closure (2026-04-29)

### V-FINAL Results

| Criterion | Status | Evidence |
|-----------|--------|----------|
| E1: AGENTS.md line count | PASS | 458 lines (82% reduction from 2,531) |
| E2: 21 child docs exist | PASS | 10 governance + 9 workflows + 2 registries |
| E3: All CI scripts pass | PASS | check_agents_md_size, check_governance_link_paths, check_skill_registry, check_dar_coverage, validate_skill_ids |
| E6: Mirror sync passes | PASS | sync_providers.py --check + sync_skills.py --check |
| E7: Anti-regrowth guardrails operational | PASS | check_agents_md_size.py WARN >480, FAIL >550 |
| E8: Size guard passes | PASS | 458 lines within thresholds |
| E10: Child-doc paths protected as FORBIDDEN_PREFIX | PASS | docs/governance/, docs/workflows/, docs/registries/ all return DENY |
| E11: Preservation invariants hold | PASS | PC-01 content/ unchanged, PC-03 knowledge/ unchanged, PC-07/PC-08 hooks match, PC-09 override_manager unchanged |
| E12: Legacy anchors resolve | PASS | All stub headings preserved |
| E13: BEQ tests pass | PASS | 10/10 trace tests pass |

### Commit History

| Commit | SHA | Phase | Description |
|--------|-----|-------|-------------|
| 0A | 9b51dab078e | Phase 0 | Protect child-doc paths as FORBIDDEN_PREFIX |
| 1A | 8e1a4993356 | Phase 1 | Create 19 governance and workflow child docs |
| 2A | 7c1e666a5f6 | Phase 2 | Add dual-read DAR parsers with fallback telemetry |
| 2B | 46fc8f72c21 | Phase 2 | Slim AGENTS.md root with stub+pointer headings |
| 3A | 6c8a2a2f6d0 | Phase 3 | Update collateral for split governance model |
| 3B | a393f8fd540 | Phase 3 | Guardrails + mirror sync + migration ledger |
| 4A | 3b7d91d61c0 | Phase 4 | Extract §12 to registry child docs with dual-read |
| 4B | 0e1211ca44a | Phase 4 | Remove §12 from root, update refs to registries |
| CL | (this commit) | Closure | Final verification + ledger update |

### Size Reduction Summary

AGENTS.md: 2,531 lines → 458 lines (82% reduction)

Sections moved to child docs: 22 (per §9 Section Completeness Table)
Sections retained verbatim in root: 10 constitutional sections
Child doc directories: docs/governance/ (10), docs/workflows/ (9), docs/registries/ (2)

---

## Metrics Obligation

Pipeline workflows using `llm.professionalize.com` carry a metrics obligation (METRICS-PLAN-001).
Changes to metrics infrastructure files (`metrics_schema.py`, `metrics_taxonomy.yaml`,
`metrics_callsite_registry.yaml`, `metrics_submitter.py`, `run_metrics.py`) must be
recorded here. The metrics governance checks in `scripts/ci/checks/` enforce compliance.
See `AGENTS.md §15` for the full metrics obligation statement.
