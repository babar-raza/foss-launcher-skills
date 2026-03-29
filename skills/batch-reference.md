Generate reference pages in bulk for all missing classes/enums in a given family + platform.

**Arguments:** `$ARGUMENTS`
**Expected format:** `{family} {platform} [--kind class|enum|all] [--limit N]`
— e.g. `slides cpp` or `slides cpp --kind enum` or `3d python --limit 10`

Defaults: `--kind all`, no limit.

## Knowledge Pre-conditions

Before generating any content, you MUST:

1. **Knowledge bootstrap**: Run `/knowledge-bootstrap {family} {platform}` and check status:
   - `STOP:partial` → halt (see printed message)
   - `REFRESHED` → STOP: "Knowledge was refreshed from upstream changes. Run /knowledge-diff to review what changed before generating content, then re-run this command."
   - `READY`, `BOOTSTRAPPED`, or `WARN:conflicts` → continue
2. **Load API surface**: Read `knowledge/{family}/{platform}/merged/api_surface.json`
   — this is the authoritative list of all types to document.
3. **Load class graph**: Read `knowledge/{family}/{platform}/merged/class_graph.json`
   — used for inheritance chains when delegating to `/new-reference-page`.
4. **Load forbidden claims**: Read `forbidden_claims` from `index.json`
   — never reference capabilities that are not implemented.

## Platform Resolution

Read `knowledge/{family}/{platform}/scout/model.yaml` to determine:
- `install_command`, `canonical_import`, `product_name`, `version`

Determine the **code fence language** from the platform:
- python → `python`
- net → `csharp`
- java → `java`
- cpp → `cpp`
- typescript → `typescript`

## Steps

### 1. Parse arguments

Parse `$ARGUMENTS` into:
- `family` — e.g. `slides`, `3d`, `cells`
- `platform` — e.g. `cpp`, `python`, `java`, `net`
- `--kind` — `class`, `enum`, or `all` (default: `all`)
- `--limit N` — process at most N entries (default: unlimited)

### 2. Load and filter api_surface.json

Read `knowledge/{family}/{platform}/merged/api_surface.json`.

Apply **platform scope rules** to determine the candidate list:

#### C++ (`cpp`) scope rules
- **Include** types where `kind == "class_specifier"` AND name does NOT match `^I[A-Z]`
  (i.e. skip I-prefixed abstract classes: IShape, ISlide, IPresentationComponent, etc.)
- **Also skip** known C++ base classes: `BaseSlide`, `GeometryShape`, `PVIObject`, `GraphicalObject`
- **Include** types where `kind == "enum_specifier"`

#### Python (`python`) scope rules
- **Include** types where `kind == "class"` AND name does NOT match `^I[A-Z]`
- **Include** types where `kind == "enum"`

#### Java (`java`) scope rules
- **Include** types where `kind` is `class`, `interface`, or `enum`
- Include I-prefixed types (Java interfaces are part of the public API)

#### .NET (`net`) scope rules
- **Include** types where `kind` is `class`, `interface`, `enum`, or `struct`
- Include I-prefixed types (C# interfaces are part of the public API)

#### TypeScript (`typescript`) scope rules
- **Include** types where `kind` is `class`, `interface`, or `enum`

Apply the `--kind` filter on top of platform scope:
- `--kind class` → keep only class/interface/struct entries (not enums)
- `--kind enum` → keep only enum entries
- `--kind all` → keep all entries that passed the platform scope rules

Apply `--limit N` after filtering (take the first N entries from the filtered list).

### 3. Check for existing pages (idempotency)

For each candidate type, the filename is the **exact class name from the repo** (PascalCase preserved):
- `PolygonModifier` → `PolygonModifier.md`
- `IShape` → `IShape.md`
- `Color3D` → `Color3D.md`

No slug transformation — the class name IS the filename stem.

Check whether `content/reference.aspose.org/en/{family}/{platform}/{ClassName}.md` already exists.
- **If it exists**: mark as `SKIP` — do not overwrite existing pages.
- **If it does not exist**: mark as `GENERATE`.

Log the tally: `Found {total} candidates: {G} to generate, {S} to skip (already exist).`

### 4. Generate pages

For each entry marked `GENERATE`, in order:

**Log progress**: `[{n}/{total_to_generate}] Generating page for {ClassName} ({kind})...`

Invoke `/new-reference-page {family} {platform} {ClassName}` passing the class data from api_surface.json.

This will:
- Build frontmatter with `categories: [Class]` or `categories: [Enum]` or `categories: [Interface]`
- Generate the body using the knowledge files
- Write to `content/reference.aspose.org/en/{family}/{platform}/{ClassName}.md`
- Attach evidence via `attach_evidence.py`

#### Enum pages — additional requirement

When generating an enum page (`kind` is `enum_specifier` / `enum`), after the standard Properties
section, add a `## Values` section with a table listing each enum member and its description:

```
## Values

| Value | Description |
|-------|-------------|
| {MemberName} | {description from api_surface.json, or empty if unavailable} |
```

All member names must come directly from the `members` array in api_surface.json for that type.
Do not invent enum values. If no members are present in api_surface.json, omit the table body
but keep the section header and column headers with a note: `*(No members found in API surface)*`.

### 5. Post-generation validation (spot-check)

After all pages are generated, run a spot-check on the first and last generated page using the audit script:

```
python scripts/pipeline/audit.py --files content/reference.aspose.org/en/{family}/{platform}/{first-ClassName}.md
python scripts/pipeline/audit.py --files content/reference.aspose.org/en/{family}/{platform}/{last-ClassName}.md
```

If either audit returns any FAIL, log a warning: `WARN: Audit failed for {ClassName} — manual review required.`
Do not halt the batch for a single failing page.

### 6. Print summary

Print a final summary in this format:

```
=== batch-reference summary ===
Family:    {family}
Platform:  {platform}
Kind:      {--kind value}
Limit:     {N or "none"}

Candidates:   {total}
Generated:    {generated}
Skipped:      {skipped} (already existed)
Errors:       {errors} (failed to generate)

Generated pages:
  - {ClassName-1}  ({kind})
  - {ClassName-2}  ({kind})
  ...

Skipped pages:
  - {ClassName-a}  (already exists)
  ...

Error pages (manual review required):
  - {ClassName-x}  ({error message})
```

## Hard Stops

- If `knowledge/{family}/{platform}/merged/api_surface.json` is missing → halt with:
  `STOP: api_surface.json not found. Run /knowledge-bootstrap {family} {platform} first.`
- If `--limit 0` is passed → halt with: `STOP: --limit must be a positive integer.`
- If S-01 path-guard returns `DENY` for any path → skip that page and log as an error.
- If `model.yaml.stale_since` is not null → halt with:
  `STOP: Knowledge model is stale. Run /knowledge-diff then /knowledge-update before generating content.`

## Idempotency Guarantee

This skill MUST NEVER overwrite an existing reference page. The check in Step 3 is mandatory
and must be performed for every candidate before invoking `/new-reference-page`. A re-run on a
fully-populated platform should produce `Generated: 0, Skipped: {N}` with no writes.

## Evidence & Commit Requirements

Each generated page receives an `evidence:` frontmatter block via `attach_evidence.py` (invoked
by `/new-reference-page`). Before committing the batch output:

1. Run `python scripts/pipeline/audit.py --files content/reference.aspose.org/en/{family}/{platform}/*.md`
   to confirm no API accuracy FAILs across all newly generated pages.
2. Include in the commit message:
   - Knowledge model SHA from `knowledge/{family}/{platform}/model.yaml`
   - `Skills invoked: [batch-reference, /new-reference-page, S-24, S-01]`
   - Count: `Generated {N} reference pages for {family}/{platform}`
