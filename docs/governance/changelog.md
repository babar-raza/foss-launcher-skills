---
# Governance child document — migration ledger
# Source: adapted from aspose.org governance refactor tracking
# Ported: 2026-05-20 (parity migration sprint)
---

# Governance Refactor — Migration Ledger

This ledger tracks structural changes to the governance document tree.

| Date | Action | Notes |
|------|--------|-------|
| 2026-04-28 | TC-01: Protected child-doc paths | Added docs/governance/, docs/workflows/, docs/registries/ to FORBIDDEN_PREFIXES |
| 2026-04-28 | TC-03/04/05: Created governance child docs | Verbatim extraction from AGENTS.md |
| 2026-04-28 | TC-06: Dual-read DAR parsers | Prefer child doc, fall back to AGENTS.md |
| 2026-04-28 | TC-07/08/09: Slim AGENTS.md root | Replaced moved sections with stub+pointer headings |
| 2026-04-28 | TC-11/12: Collateral updates | Updated instruction files, governance refs, skill refs |
| 2026-04-28 | TC-13/14/15: Guardrails + sync + ledger | CI scripts, mirror sync, this ledger |

## Verification Criteria

| Criterion | Description |
|-----------|-------------|
| E1 | AGENTS.md line count within threshold |
| E2 | All child docs exist in expected directories |
| E3 | All CI governance scripts pass |
| E10 | Child-doc paths protected as FORBIDDEN_PREFIX |
| E11 | Preservation invariants hold (content unchanged, hooks intact) |
| E12 | Legacy anchors resolve via stub headings |

## Size Reduction Summary

Governance sections moved to child docs per section completeness table.
Child doc directories: `docs/governance/`, `docs/workflows/`, `docs/registries/`.

---

## Recording Obligation

Changes to governance infrastructure files must be recorded in this ledger.
CI governance checks in `scripts/ci/checks/` enforce compliance.
