# Compatibility Shim Policy

Status: Phase 7 foundation artifact

## Purpose

The standalone repo should remain cleaner than the embedded aspose.org implementation. Legacy path compatibility is allowed only when it preserves real user behavior or unblocks existing skill contracts.

## Shim Eligibility

Add a compatibility shim only when at least one condition is true:

- A registered skill still documents the legacy path.
- A provider mirror or command refers to the legacy path.
- A user-facing workflow is known to invoke the legacy path.
- A test or CI check expects the legacy path.

Do not add a shim when:

- The legacy path is only a stale report artifact.
- The dependency is website-only and should be represented as an external content repo contract.
- Updating the skill documentation to the standalone canonical path is safer.

## Shim Requirements

Each shim must:

- be thin and deterministic;
- import or delegate to the standalone canonical implementation;
- contain no business logic beyond argument forwarding and compatibility warnings;
- have at least one test or smoke check;
- document the canonical replacement path;
- avoid writing to content unless the canonical command already enforces dry-run/output-root safety.

## Mapping Table Schema

Use this schema in future evidence or docs:

```yaml
legacy_path:
canonical_path:
reason:
referenced_by:
shim_required: true|false
test_path:
deprecation_note:
```

## Preferred Resolution Order

1. Update stale docs or registry references to the standalone canonical path.
2. Add tests for the canonical path.
3. Add a compatibility shim only if a real workflow still needs the old path.
4. Record a deprecation note if the shim should eventually be removed.

## Safety Rules

- Never copy site-only Hugo/theme/content assumptions into a shim.
- Never hide a missing implementation behind a shim that exits successfully without doing the work.
- Never add a shim without an evidence file explaining why it exists.

## Done Criteria For Implementations

- Every shim has a mapping record.
- Every shim has targeted verification.
- The canonical standalone path remains documented as the preferred entrypoint.
