# S-36: Cross-Platform — Family Consistency Check

**Arguments**: $ARGUMENTS
Expected format: `{family}`

## Purpose
Verify consistency across all platforms within the same product family. Detect discrepancies in
format support, API surface, features, and limitations. Produces a human-readable report for
review and updates each platform's `index.json` with a `platform_consistency` section.

## Pre-conditions
1. At least 2 platforms must have merged knowledge for the given family.
2. `knowledge/{family}/*/merged/index.json` must exist for each platform.

## Steps

1. **Discover platforms**: Scan `knowledge/{family}/` for platform directories with `merged/index.json`.
   Collect the list of platforms (e.g., `python`, `net`, `java`, `cpp`, `typescript`).

2. **Load all indices**: Read `index.json` for each platform into memory.

3. **Compare format matrices**:
   - Load `formats.import[]` and `formats.export[]` from each platform's `index.json`.
   - A **discrepancy** exists when a format appears as supported in one platform but is listed in
     `not_implemented[]` or absent from the format arrays in another platform.
   - Flag with severity: `INFO` (naming difference only), `WARN` (one platform has caveat, others don't),
     `GAP` (format present in one, entirely absent in another).
   - Record in report under `## Format Support Alignment`.

4. **Compare API surface**:
   - Load `classes[]` from each platform's `index.json`.
   - **Name normalization**: Map between naming conventions before comparing:
     - PascalCase (C#, Java) ↔ snake_case (Python) — e.g. `PolygonModifier` ↔ `polygon_modifier`
     - Apply the rule: strip underscores and lowercase both sides before comparing.
   - A **discrepancy** exists when a class (after normalization) appears in one platform's `classes[]`
     but not in any other platform's normalized class list.
   - Flag as `MISSING` (class absent from ≥1 platform) or `NAMING_ONLY` (exists in all, names differ).
   - Record in report under `## API Surface Discrepancies`.

5. **Compare limitations**:
   - Load `not_implemented[]` from each platform's `index.json`.
   - A **gap** exists when a limitation appears in one platform but is not documented in another,
     suggesting the other platform may have implemented it (positive gap) or just not documented it.
   - Record in report under `## Limitation Gaps` with a note: "confirmed missing | not checked".

6. **Compare install/runtime requirements**:
   - Verify that the `install` field for each platform specifies a non-null entry for its own
     platform field (e.g., Python must have a non-null `pip`).
   - Note version differences if `model.yaml` version fields differ across platforms.
   - Record in report under `## Runtime Requirements`.

7. **Write consistency report** to `knowledge/{family}/_consistency.md`.

8. **Update each platform's index.json** with a `platform_consistency` section:
   ```json
   "platform_consistency": {
     "checked_against": ["python", "net", ...],
     "format_gaps": ["FBX export: missing in net"],
     "api_gaps": ["PolygonModifier: missing in typescript"],
     "last_checked": "{ISO timestamp}"
   }
   ```

## Report format
```markdown
# Cross-Platform Consistency: Aspose.{Family}
Platforms: {list}
Checked: {ISO timestamp}

## Format Support Alignment
| Format | Python | TypeScript | .NET |
|--------|--------|-----------|------|
| OBJ import | ✓ | ✓ | ✓ |
| FBX export | ✗ (NotImpl) | ✗ (NotImpl) | ? (not checked) |

## API Surface Discrepancies
- `PolygonModifier` (Python): no equivalent found in TypeScript [GAP]
- `.NET Scene.Open()` vs Python `scene.open()`: naming convention only [NAMING_ONLY — OK]

## Limitation Gaps
- FBX export not implemented: confirmed Python, TypeScript; not checked .NET

## Runtime Requirements
- Python: 3.8+; .NET: 6.0+; TypeScript: Node 18+
```

## Discrepancy Severity Guide

| Severity | Meaning | Action |
|----------|---------|--------|
| `INFO` | Naming difference only — same feature | No action required |
| `WARN` | One platform has a caveat; others don't document it | Review; add caveat to other platforms if applicable |
| `GAP` | Feature/class absent from ≥1 platform | Escalate; may indicate missing implementation or missing documentation |

## Post-conditions
- `knowledge/{family}/_consistency.md` exists.
- Discrepancies are clearly documented with platform-specific details and severity codes.
- Each processed platform's `index.json` has a `platform_consistency` section with `last_checked` timestamp.
- Any `GAP`-severity discrepancy triggers a `WARN` in the report summary. Human review recommended for `GAP` items.
