---
name: batch-reference
description: >
  Generate reference pages in bulk for all missing classes/enums
args: "{family} {platform}"
---

> Cross-skill references like `/knowledge-bootstrap` refer to sibling skills in this directory.

<!-- CONTRACT: scripts/pipeline/batch_reference.py (backing script for headless/CI batch runs)
     purpose: generate template-based skeleton reference pages from api_surface.json without LLM
     cli: python scripts/pipeline/batch_reference.py {family} {platform} [--kind class|enum|all] [--limit N] [--dry-run]
     postcondition: applies same platform scope rules as this skill (kind values match tree-sitter output)
     postcondition: idempotent — skips existing pages; re-run on populated platform yields Generated: 0
     postcondition: prints S-62 summary format (Candidates / Generated / Skipped / Errors)
     verified: 2026-04-07
-->

# S-62: Batch Reference — Generate Reference Pages in Bulk

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

> **Skill context gate** — run before step 1:
> ```bash
> PYTHONPATH=scripts/pipeline .venv/Scripts/python scripts/pipeline/skill_context.py begin --skill S-62 --scope "*"
> ```


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
- **Include** types where `kind == "class_definition"` AND name does NOT match `^I[A-Z]`
  AND the class is NOT an enum subclass (see enum rule below)
- **Include** types where `kind == "class_definition"` AND the class inherits from one of:
  `Enum`, `IntEnum`, `StrEnum`, `Flag`, `IntFlag`, `enum.Enum`, `enum.IntEnum`, `enum.StrEnum`,
  `enum.Flag`, `enum.IntFlag` — these are the Python enum classes

#### Java (`java`) scope rules
- **Include** types where `kind` is `"class_declaration"`, `"interface_declaration"`, or `"enum_declaration"`
- Include I-prefixed types (Java interfaces are part of the public API)

#### .NET (`net`) scope rules
- **Include** types where `kind` is `"class_declaration"`, `"interface_declaration"`,
  `"enum_declaration"`, or `"struct_declaration"`
- Include I-prefixed types (C# interfaces are part of the public API)

#### TypeScript (`typescript`) scope rules
- **Include** types where `kind` is `"class_declaration"`, `"interface_declaration"`, or `"enum_declaration"`

> **KIND Reference** — actual values emitted by the scanner (`api_surface.py` sets `"kind": cnode.type`):
>
> | Platform | Class kinds | Enum kind |
> |----------|------------|-----------|
> | `cpp`    | `class_specifier`, `struct_specifier` | `enum_specifier` |
> | `python` | `class_definition` | `class_definition` (detect via base class) |
> | `java`   | `class_declaration`, `interface_declaration` | `enum_declaration` |
> | `net`    | `class_declaration`, `interface_declaration`, `struct_declaration`, `record_declaration` | `enum_declaration` |
> | `typescript` | `class_declaration`, `interface_declaration`, `type_alias_declaration` | `enum_declaration` |
>
> Source of truth: `scripts/pipeline/extraction/tree_helpers.py` `_CLASS_TYPES` dict.

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

Invoke the batch generation script:

```bash
.venv/Scripts/python scripts/pipeline/batch_reference.py {family} {platform}
```

The script generates all class pages using templates from `api_surface.json`. For each page it:
- Builds frontmatter including `provenance:` block (`content_origin: skill-generated`, `content_created_at`) and `evidence:` block
- Generates the body sections (Overview, Constructors, Methods, Properties, etc.)
- Writes to `content/reference.aspose.org/en/{family}/{platform}/{ClassName}.md`
- Calls `attach_evidence()` with `force=True` to replace the template evidence block with
  tokenised API citations and auto-grade the page (`grade:`, `graded_at:`, etc.)

> **Contract note (Fix 10, 2026-04-07)**: Prior to Fix 8, `batch_reference.py` wrote pages
> without a `provenance:` block and without calling `attach_evidence()`. This meant reference
> pages lacked grading and violated Control 1 (AGENTS.md §6.3). Fix 8 corrected both gaps.
> The skill spec previously documented invocation via `/new-reference-page` per class — the
> actual implementation uses the batch script directly. This note records the correction.

**D-1/D-2/D-3 enforcement** (all pages, non-negotiable):
- **D-1 description**: Use `class.doc` from api_surface.json. If absent, write `[No documentation available — class summary not captured by scout]`. Do NOT invent a description.
- **D-2 return types**: Each method's return type MUST come from `method.return_type` in api_surface.json. Non-empty, non-void → show `→ {return_type}`. Omit or show `→ None` for void/empty.
- **D-3 access mode**: Each property Access value MUST be derived from `property.writable`: `true` → `Read/Write`, `false`/absent → `Read`. Do NOT default all properties to `Read`.

#### Enum pages — additional requirement

When generating an enum page (`kind` is `enum_specifier` / `enum`), after the standard Properties
section, add a `## Values` section with a table listing each enum member and its description:

```

> **Skill context close** — run after the last step:
> ```bash
> PYTHONPATH=scripts/pipeline .venv/Scripts/python scripts/pipeline/skill_context.py end --skill S-62 --status completed
> ```

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
.venv/Scripts/python scripts/pipeline/audit.py --files content/reference.aspose.org/en/{family}/{platform}/{first-ClassName}.md
.venv/Scripts/python scripts/pipeline/audit.py --files content/reference.aspose.org/en/{family}/{platform}/{last-ClassName}.md
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

## Update Mode (--update flag)

After a knowledge refresh (S-14), use `--update` to regenerate only the reference pages whose
classes appear in `knowledge_delta.json modified_apis`:

```bash
.venv/Scripts/python scripts/pipeline/batch_reference.py {family} {platform} --update
.venv/Scripts/python scripts/pipeline/batch_reference.py {family} {platform} --update --dry-run  # preview only
```

**Behavior in `--update` mode**:
- Reads `knowledge/{family}/{platform}/merged/knowledge_delta.json` to get `modified_apis` list
- Regenerates pages only for classes in `modified_apis` (overwrites existing pages)
- Skips all other classes (preserves unchanged pages)
- New classes (in `api_surface.json` but no existing page) are always generated
- Calls `attach_evidence()` and grade_writer on updated pages — identical to new-page generation
- Prints summary: `Updated N pages, generated M new pages, skipped K unchanged`
- **If `knowledge_delta.json` is absent**: prints `WARN: knowledge_delta.json not found; falling back to default mode`
  and degrades to standard behavior (skip existing pages, generate only new ones)

Use `--update` in the maintenance chain after S-14 (knowledge-update) to keep reference pages current.

## Idempotency Guarantee

**Default mode** (no `--update`): this skill MUST NEVER overwrite an existing reference page.
The check in Step 3 is mandatory and must be performed for every candidate before invoking
`/new-reference-page`. A re-run on a fully-populated platform should produce `Generated: 0, Skipped: {N}` with no writes.

**`--update` mode**: intentionally overwrites pages whose classes appear in `modified_apis`.
Idempotency is preserved for unchanged pages — only modified classes are regenerated.

## Evidence & Commit Requirements

Each generated page receives an `evidence:` frontmatter block via `attach_evidence.py` (invoked
by `/new-reference-page`). Before committing the batch output:

1. Run `python scripts/pipeline/audit.py --files content/reference.aspose.org/en/{family}/{platform}/*.md`
   to confirm no API accuracy FAILs across all newly generated pages.
2. Include in the commit message:
   - Knowledge model SHA from `knowledge/{family}/{platform}/model.yaml`
   - `Skills invoked: [batch-reference, /new-reference-page, S-24, S-01]`
   - Count: `Generated {N} reference pages for {family}/{platform}`
