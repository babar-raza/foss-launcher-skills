# Pipeline Registry Reference

Status: Current
Audience: Contributor
Canonical reference: this page
Last code-backed audit: 2026-05-30

`scripts/pipeline/config/registry.yaml` is the machine-readable registry for pipeline scripts.

## Registry Fields

| Field | Purpose |
|---|---|
| `path` | Script path. |
| `kind` | `entrypoint`, `library`, or `one-shot`. |
| `lifecycle` | `active`, `maintenance`, or `deprecated`. |
| `public_entrypoint` | Whether the script exposes a public command surface. |
| `cli_contract` | Stability of CLI contract. |
| `owner_domain` | Owning subsystem. |
| `backing` | Skill, workflow, or internal backing. |
| `test_targets` | Tests that cover the script. |
| `requires_test` | Whether test coverage is mandatory. |

## CI Enforcement

The content audit workflow runs pipeline registration checks and can fail on test gaps.

See [Testing and CI](../development/testing.md).
