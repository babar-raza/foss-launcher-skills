---
name: batch-reference
id: S-67
description: >
  Generate reference pages in bulk for all missing classes and enums in a given
  family and platform. Uses api_surface.json as the authoritative candidate list.
  Idempotent — skips existing pages by default.
args: "{family} {platform} [--kind class|enum|all] [--limit N] [--update]"
---

# S-67: Batch Reference — Generate Reference Pages in Bulk

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
- **Also skip** known C++ base classes: `BaseSlide`, `GeometryShape`, `PVIObject`, `GraphicalObject`
- **Include** types where `kind == "enum_specifier"`

#### Python (`python`) scope rules
- **Include** types where `kind == "class_definition"` AND name does NOT match `^I[A-Z]`
  AND the class is NOT an enum subclass
- **Include** types where `kind == "class_definition"` AND the class inherits from one of:
  `Enum`, `IntEnum`, `StrEnum`, `Flag`, `IntFlag`, `enum.Enum`, `enum.IntEnum`, `enum.StrEnum`,
  `enum.Flag`, `enum.IntFlag`

#### Java (`java`) scope rules
- **Include** types where `kind` is `"class_declaration"`, `"interface_declaration"`, or `"enum_declaration"`

#### .NET (`net`) scope rules
- **Include** types where `kind` is `"class_declaration"`, `"interface_declaration"`,
  `"enum_declaration"`, or `"struct_declaration"`

#### TypeScript (`typescript`) scope rules
- **Include** types where `kind` is `"class_declaration"`, `"interface_declaration"`, or `"enum_declaration"`

Apply the `--kind` filter on top of platform scope:
- `--kind class` → keep only class/interface/struct entries (not enums)
- `--kind enum` → keep only enum entries
- `--kind all` → keep all entries that passed the platform scope rules

Apply `--limit N` after filtering.

### 3. Check for existing pages (idempotency)

For each candidate type, the filename is the **exact class name from the repo** (PascalCase preserved):
- `PolygonModifier` → `PolygonModifier.md`

Check whether `$CONTENT_REPO_PATH/content/reference.aspose.org/en/{family}/{platform}/{ClassName}.md` already exists.
- **If it exists**: mark as `SKIP` — do not overwrite existing pages.
- **If it does not exist**: mark as `GENERATE`.

Log the tally: `Found {total} candidates: {G} to generate, {S} to skip (already exist).`

### 4. Generate pages

For each entry marked `GENERATE`, invoke the batch generation script:

```bash
python scripts/pipeline/commands/content/batch_reference.py {family} {platform}
```

The script generates class pages using templates from `api_surface.json`. For each page it:
- Builds frontmatter including `provenance:` block and `evidence:` block
- Generates the body sections (Overview, Constructors, Methods, Properties, etc.)
- Writes to `$CONTENT_REPO_PATH/content/reference.aspose.org/en/{family}/{platform}/{ClassName}.md`
- Calls `attach_evidence()` to replace the template evidence block with API citations and grade the page

**D-1/D-2/D-3 enforcement** (all pages, non-negotiable):
- **D-1 description**: Use `class.doc` from api_surface.json. If absent, write `[No documentation available]`. Do NOT invent a description.
- **D-2 return types**: Each method's return type MUST come from `method.return_type` in api_surface.json.
- **D-3 access mode**: Each property Access value MUST be derived from `property.writable`: `true` → `Read/Write`, `false`/absent → `Read`.

#### Enum pages — additional requirement

When generating an enum page, after the standard Properties section, add a `## Values` section:

```markdown
## Values

| Value | Description |
|-------|-------------|
| {MemberName} | {description from api_surface.json, or empty if unavailable} |
```

All member names must come directly from the `members` array in api_surface.json.

### 5. Post-generation validation (spot-check)

After all pages are generated, run a spot-check on the first and last generated page:

```bash
python scripts/pipeline/commands/content/audit.py \
  --files $CONTENT_REPO_PATH/content/reference.aspose.org/en/{family}/{platform}/{first-ClassName}.md
python scripts/pipeline/commands/content/audit.py \
  --files $CONTENT_REPO_PATH/content/reference.aspose.org/en/{family}/{platform}/{last-ClassName}.md
```

If either audit returns any FAIL, log a warning and route to `/publish-readiness-review`.

### 6. Print summary

```
=== batch-reference summary ===
Family:    {family}
Platform:  {platform}
Kind:      {--kind value}
Limit:     {N or "none"}

Candidates:   {total}
Generated:    {generated}
Skipped:      {skipped} (already existed)
Errors:       {errors}
```

## Hard Stops

- If `api_surface.json` is missing → halt: `STOP: api_surface.json not found. Run /knowledge-bootstrap first.`
- If `model.yaml.stale_since` is not null → halt: `STOP: Knowledge model is stale. Run /knowledge-diff then /knowledge-update first.`

## Update Mode (--update flag)

After a knowledge refresh (S-14), use `--update` to regenerate only pages for classes in `knowledge_delta.json modified_apis`:

```bash
python scripts/pipeline/commands/content/batch_reference.py {family} {platform} --update
python scripts/pipeline/commands/content/batch_reference.py {family} {platform} --update --dry-run  # preview only
```

## Idempotency Guarantee

**Default mode**: NEVER overwrites an existing reference page. A re-run on a fully-populated platform
should produce `Generated: 0, Skipped: {N}` with no writes.

**`--update` mode**: intentionally overwrites pages for modified classes only.

## Evidence & Commit Requirements

Before committing the batch output:

1. Run `python scripts/pipeline/commands/content/audit.py --files $CONTENT_REPO_PATH/content/reference.aspose.org/en/{family}/{platform}/*.md`
2. Include in the commit message:
   - Knowledge model SHA from `knowledge/{family}/{platform}/model.yaml`
   - `Skills invoked: S-67, S-55, S-24, S-01`
   - Count: `Generated {N} reference pages for {family}/{platform}`
