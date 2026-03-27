# S-36: Cross-Platform — Family Consistency Check

**Arguments**: $ARGUMENTS
Expected format: `{family}`

## Purpose
Verify consistency across all platforms within the same product family. Detect discrepancies in format support, API surface, features, and limitations.

## Pre-conditions
1. At least 2 platforms must have merged knowledge for the given family
2. `knowledge/{family}/*/merged/index.json` must exist for each platform

## Steps

1. **Discover platforms**: Scan `knowledge/{family}/` for platform directories with `merged/index.json`
2. **Load all indices**: Read `index.json` for each platform
3. **Compare format matrices**:
   - Same format should have same import/export support across platforms
   - Flag differences with caveats (e.g., "FBX export: Python=NotImpl, TypeScript=NotImpl, .NET=not checked")
4. **Compare API surface**:
   - Core classes should exist across all platforms (with naming convention differences)
   - Map naming: PascalCase (C#) ↔ snake_case (Python) ↔ camelCase (JS/TS)
   - Flag classes present in one platform but missing in another
5. **Compare limitations**:
   - Same limitations should appear across platforms
   - Flag cases where one platform implements what another doesn't
6. **Compare install/runtime requirements**:
   - Verify version consistency
7. **Write consistency report** to `knowledge/{family}/_consistency.md`

## Report format
```markdown
# Cross-Platform Consistency: Aspose.{Family}
Platforms: {list}

## Format Support Alignment
| Format | Python | TypeScript | .NET |
|--------|--------|-----------|------|
| OBJ import | ✓ | ✓ | ✓ |
| FBX export | ✗ (NotImpl) | ✗ (NotImpl) | ? |

## API Surface Discrepancies
- Python has `PolygonModifier` class; TypeScript does not
- .NET `Scene.Open()` vs Python `Scene.open()` — naming only (OK)

## Limitation Gaps
- FBX export not implemented: confirmed Python, TypeScript; not checked .NET
```

## Post-conditions
- `knowledge/{family}/_consistency.md` exists
- Discrepancies are clearly documented with platform-specific details
- Each `index.json` is updated with `platform_consistency` section
