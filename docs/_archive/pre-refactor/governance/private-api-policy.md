# Archived Document

Archived: 2026-05-30

Reason: Superseded by the docs architecture refactor. This file is retained for history only; do not use it as current operating guidance.

Successor: See docs/README.md for the current documentation map and canonical references.

Original path: docs/_archive/pre-refactor/governance/private-api-policy.md

---

# Private API Usage Policy

**Status**: Active
**Effective**: 2026-05-29
**Tracking**: TC-HCR-002

---

## Rule

Private API members (Python `_underscore` convention, Java `@Internal`, etc.) **must not appear in published content** unless the member is documented in the product's `knowledge/{family}/{platform}/merged/workarounds.json` file with a stated reason and no public alternative exists.

When a private member IS listed in `workarounds.json`, the `private_api_usage` evaluator automatically downgrades the finding from FAIL to INFO. Pages with only INFO-level private-API findings are considered compliant.

---

## When a Workaround is Acceptable

A private API workaround is acceptable in published content when **all** of the following are true:

1. **No public alternative exists** — the upstream library provides no public method, property, or factory for the same operation.
2. **The workaround is documented** — an entry exists in `knowledge/{family}/{platform}/merged/workarounds.json` with `class`, `private_member`, and `reason` fields.
3. **The evaluator confirms INFO level** — running `content-eval` on the page shows the private-API finding at INFO severity (not WARN or FAIL).
4. **The reason is accurate** — the `reason` field in `workarounds.json` correctly describes why the public API is insufficient (e.g., "returns defensive copy, append is a no-op").

---

## Known Approved Workarounds

| Product | Class | Private Member | Reason |
|---------|-------|----------------|--------|
| 3d/python | `Mesh` | `_control_points` | `control_points` property returns a defensive copy; `append()` is a no-op; no public vertex-mutation API exists in upstream Python library |

---

## Adding a New Workaround

1. Verify no public alternative exists (check clone cache + api_surface.json).
2. Add entry to `knowledge/{family}/{platform}/merged/workarounds.json`:
   ```json
   {
     "class": "ClassName",
     "private_member": "_member_name",
     "reason": "Explanation of why public API is insufficient.",
     "tracking": "BACKLOG-ID",
     "added": "YYYY-MM-DD"
   }
   ```
   Note: `knowledge/` is gitignored; this is a local-only unblock. Document in backlog.
3. Run `content-eval` to confirm evaluator downgrades to INFO.
4. Add a backlog entry tracking the upstream gap.

---

## Relationship to Evaluator

The evaluator is `scripts/pipeline/content_eval/evaluators/private_api_usage.py`. It loads `workarounds.json` at startup and matches detected private members against the known-workaround list. If a match is found, the finding severity is INFO (not FAIL). This behavior is intentional and permanent — do not modify this evaluator to raise the severity for approved workarounds.
