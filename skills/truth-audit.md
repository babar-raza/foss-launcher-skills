---
name: truth-audit
id: S-47
description: >
  Line-by-line verification of every API claim in content files against
  api_surface.json. Extracts class names, method names, property names,
  constructor signatures, enum values, types, install commands, and format
  claims, then verifies each against the knowledge model. Produces a
  structured FAIL/WARN/PASS report.
args: "{family} {platform}"
---

# S-47: Truth Audit — Member-Level API Verification

**Arguments**: $ARGUMENTS
Expected format: `{family} {platform}` — e.g. `3d java`

## Purpose

Verify every API claim in content files against `api_surface.json` at the **member level** — not just class existence but individual methods, properties, constructor signatures, enum values, and types. This catches fabricated APIs that pass class-level checks (S-32, S-33, content-check).

## Pre-conditions

1. `knowledge/{family}/{platform}/merged/api_surface.json` must exist
2. `knowledge/{family}/{platform}/merged/index.json` must exist
3. Knowledge must not be stale (`stale: false`)

## Knowledge Files to Load

Read ALL of these before scanning any content:

1. **`api_surface.json`** — THE authority for class/method/property/enum verification
2. **`index.json`** — `forbidden_claims`, `classes` list, `not_implemented` list
3. **`install.md`** — canonical install command
4. **`formats.md`** — format import/export support
5. **`limitations.md`** — methods that throw NotImplementedError
6. **`model.yaml`** — version, product_name, repo_sha
7. **FL snippets** (`knowledge/{family}/{platform}/fl/snippet_*.*`) — secondary source for verified code patterns

Read `api_surface.json` IN FULL. Do not skim. Every verification depends on this file.

## Surface Quality Check

Before scanning content, read `index.json` → `api_coverage` → `surface_tier`.

Output a confidence header at the top of the report:

```
API Surface Quality: TIER {surface_tier}
  Classes: {total_classes} | Methods: {method_pct}% | Properties: {property_pct}% | Enums: {with_enums}
  Audit confidence: {HIGH if tier=1, MODERATE if tier=2, LOW if tier=3}
```

Adjust verification behavior by tier:
- **Tier 1** (method_pct ≥ 70%): FAIL on missing methods, properties, and enum values
- **Tier 2** (method_pct 40–69%): FAIL on missing methods; WARN on missing properties and enum values
- **Tier 3** (method_pct < 40%): WARN on everything (no FAIL for member-level claims); note that results are unreliable

## Content Files to Scan

Glob all of these:

- `content/products.aspose.org/en/{family}/{platform}/_index.md`
- `content/blog.aspose.org/{family}/{platform}/**/index.md`
- `content/reference.aspose.org/en/{family}/{platform}/*.md`

If `{platform}` does not have a products page (family-level pages like `content/products.aspose.org/en/{family}/_index.md` that mention the platform), check those too.

## Extraction Rules

For each content file, extract every API identifier:

### From code blocks (` ``` ` fenced blocks)

1. **Method calls**: `obj.methodName(`, `ClassName.methodName(` → extract class + method name
2. **Property access**: `obj.propertyName`, `obj.propertyName =` → extract property name
3. **Constructor calls**: `new ClassName(args)` (Java/C#/TS) or `ClassName(args)` (Python) → extract class + parameter count/types
4. **Import statements**: `import {X} from 'pkg'`, `from pkg import X`, `using Namespace` → extract package paths
5. **Enum usage**: `EnumName.VALUE`, `EnumName.value` → extract enum + value
6. **Static method/field access**: `ClassName.CONSTANT`, `ClassName.staticMethod()` → extract class + member

### From markdown tables

7. **Property tables**: `| name | type | access | description |` rows → extract property name + type
8. **Method tables**: `| method | return | description |` rows → extract method name + return type
9. **Constructor tables**: `| constructor | description |` rows → extract signature
10. **Enum value tables**: `| value | description |` rows → extract enum values

### From prose

11. **API claims**: "the X class provides Y method", "X has properties A, B, C"
12. **Format claims**: "supports X import/export", "X format is supported"
13. **Install commands**: `pip install`, `npm install`, `dotnet add package`, Maven `<dependency>`

## Verification Rules

For each extracted token, verify against knowledge:

### FAIL conditions (must fix before commit)

1. **Method not found**: `ClassName.methodName` where class exists in api_surface but method is not in its `methods[]` array — and the class has a NON-EMPTY methods array
2. **Property not found**: `ClassName.propertyName` where class exists but property is not in its `properties[]` array — and the class has a NON-EMPTY properties array
3. **Wrong type**: Property table states type `X` but api_surface shows type `Y`
4. **Wrong constructor signature**: Constructor parameter count or types don't match any constructor in api_surface
5. **Fabricated enum value**: Enum class exists but value is not in `enum_members[]`
6. **Wrong install command**: Does not match `install.md`
7. **Contradicted format claim**: Content claims format support that contradicts `formats.md`
8. **Forbidden claim matched**: Content matches an entry in `index.json` → `forbidden_claims`
9. **Class not found**: Class name referenced in content is not in api_surface AND not in `index.json` → `classes`
10. **Wrong parameter order**: Method parameters exist but documented in wrong order vs api_surface

### WARN conditions (flag for review)

1. **Not-implemented documented as working**: Method exists in api_surface but is in `limitations.md` not-implemented list, and content documents it as functional (no warning/caveat)
2. **Unverifiable method/property**: Class exists but has EMPTY `methods[]`/`properties[]` arrays in api_surface (sparse extraction). Content claims specific members. Check FL snippets as secondary source — if confirmed there, PASS. If not found anywhere, WARN as UNVERIFIABLE.
3. **Enum values unverifiable**: Enum class exists but has no `enum_members` in api_surface. Check FL snippets.
4. **Inherited member claimed on child**: Method/property exists on parent class but content documents it directly on child class without noting inheritance

### PASS conditions

1. **Class found**: Class name exists in api_surface
2. **Method found**: Method exists on the class (or on its parent class via class_graph)
3. **Property found**: Property exists with correct type
4. **Constructor found**: Matching signature exists
5. **Enum value found**: Value exists in enum_members
6. **Install command matches**: Exact match with install.md
7. **Format claim consistent**: Matches formats.md

## Inheritance Handling

When a method/property is not found directly on a class:
1. Look up the class in `class_graph` (from index.json or api_surface bases)
2. Check parent class for the member
3. If found on parent → PASS (but note inheritance)
4. If not found on parent either → continue up the chain
5. If not found anywhere in hierarchy → FAIL

## Output Format

Write the report to `reports/audit/{family}-{platform}-truth-{date}.md`:

```markdown
# Truth Audit: {family}/{platform}
Date: {YYYY-MM-DD}
Knowledge SHA: {repo_sha}
Knowledge version: {version}
Files checked: {N}

## Summary
| Metric | Count |
|--------|-------|
| Total API claims checked | N |
| PASS | N |
| FAIL | N |
| WARN (unverifiable) | N |
| WARN (not-implemented) | N |
| Install check | PASS/FAIL |
| Format check | PASS/FAIL |

## FAIL — Must Fix

### {relative-file-path}
- **Line {N}**: `ClassName.methodName()` — method does not exist on {ClassName} in api_surface.json. {ClassName}.methods = [{actual methods}]
- **Line {N}**: Property `propName` type claimed as `{X}`, actual type is `{Y}` per api_surface.json
- **Line {N}**: `EnumName.VALUE` — value not found. Actual values: [{actual values}]
- **Line {N}**: Constructor `new Class(a, b, c)` — no 3-param constructor. Available: [{actual constructors}]
- **Line {N}**: Install command `{wrong}` — should be `{correct}` per install.md
- **Line {N}**: Claims {format} export is supported — formats.md says {truth}

### {next-file-path}
...

## WARN — Review

### {file-path}
- **Line {N}**: `ClassName.methodName()` — class has empty methods array in api_surface (UNVERIFIABLE)
- **Line {N}**: `Mesh.union()` — exists but throws NotImplementedError per limitations.md

## Statistics
- Files with 0 FAILs: {list}
- Files with FAILs: {list with count}
- api_surface coverage: {N} classes with populated members / {N} total classes
```

## Post-conditions

1. Report written to `reports/audit/`
2. **No content with FAIL findings may be committed** — all FAILs must be resolved first
3. WARN findings should be reviewed — not-implemented methods need caveats in content, unverifiable claims need FL snippet confirmation or removal

## Relationship to Other Skills

| Skill | Layer | What it catches |
|-------|-------|----------------|
| **S-47 truth-audit** | Member-level | Fabricated methods, properties, wrong types, wrong signatures |
| S-32 content-audit | Claim-level | Claims that contradict known facts in claims.json |
| S-33 change-guard | Block-level | Pre-write check for single text blocks |
| content-check | Structure-level | Frontmatter, file paths, class-name existence |

**Recommended chain**: Generate → **S-38** → fix FAILs → S-32 → S-33 → write

## Re-run Policy

This skill is designed to be re-run. After fixing FAILs, re-run to confirm all fixes and check for regressions. A clean run (0 FAILs) is the gate for commit readiness.
