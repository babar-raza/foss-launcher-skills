# `/readme-refresh` — README Template Contract

> **Role**: the durable, versioned, in-repo record of the README structure `/readme-refresh`
> (S-120) generates and verifies. Fixes SW-F from the production-hardening design
> (`readme-refresh-hardening-and-regen-2026-08-30`): "the authoritative Template lives in a
> 1.8MB, 20,903-line, gitignored, single-machine plan file. Nothing forces the skill doc, the
> check battery, and the Template to move together." This file and its machine-readable sibling
> (`data/readme_template_contract.json`) are that fix — both are checked for real, mechanical
> agreement with the check battery's own code by
> `scripts/ci/checks/check_readme_template_contract_parity.py` (TC-34,
> `readme-refresh-trackb-and-followon-2026-09-01`).
>
> This file does not restate every one of the ~110 individual `check_*` rules — that duplication
> would itself become a second, competing source of truth, exactly the failure mode SW-F names.
> It records the one structural fact every consumer (the composing agent, the check battery, this
> doc, `scripts/pipeline/config/registry.yaml`'s own `change_impact` description) must agree on:
> **which sections exist, in what order, and how many checks currently enforce the rest.**

## Required sections, in order

Every generated README must contain exactly these ten `##` sections, in this order (enforced by
`check_required_sections_present` / `check_heading_title_case` in
`scripts/pipeline/commands/foss/readme_refresh_checks.py`, source of truth:
`_REQUIRED_SECTIONS`):

1. At a Glance
2. Key Capabilities
3. Installation
4. Dependencies
5. Quick Start
6. API Reference
7. Documentation & Resources
8. Scope and Limitations
9. Development and Testing
10. License

## Optional section

**Additional Examples** sits between Quick Start and API Reference when present. It is
*vacuously* satisfied when absent — required only when a product has enough real snippets to
justify a dedicated section, a content-quality judgment call the check battery deliberately does
not try to automate. `cells/cpp` is the one portfolio product that legitimately has none.

## Check-function count

The real, current count of `check_*` functions in `readme_refresh_checks.py` is recorded in
`data/readme_template_contract.json`'s `check_function_count.value` field, and independently
re-derived (via `grep -c "^def check_"`) every time the parity check runs — never trusted as a
static fact. `scripts/pipeline/config/registry.yaml`'s S-120 `change_impact` field carries the
same number in prose form; both are checked for agreement with the real code, not with each
other, so a drift in either direction fails loudly instead of silently compounding (the exact
defect class `RC-check-count-doc-drift-fix` closed once, 2026-08-30, that this contract prevents
from recurring unnoticed).

## How to change this contract

Adding, removing, or reordering a required section is a real product decision, not a
documentation edit — it changes what `check_required_sections_present` accepts for all 31+
products. Update `_REQUIRED_SECTIONS` in `readme_refresh_checks.py` first, then this file and
`data/readme_template_contract.json` to match, then re-run
`check_readme_template_contract_parity.py` to confirm all three agree before committing.
