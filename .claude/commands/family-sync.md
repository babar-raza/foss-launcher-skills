# S-48: Family Sync — Update Family Page for All Launched Platforms

**Arguments**: $ARGUMENTS
Expected format: `{family}` — e.g. `email` or `3d`

## Purpose

Update the family-level `_index.md` at `content/products.aspose.org/en/{family}/_index.md`
so its `head_description`, `description`, and `overview.content` fields accurately reflect
all currently launched platforms. Reads knowledge from each platform, computes shared
capabilities, and rewrites the three text fields to be platform-agnostic.

## Pre-conditions

1. **Knowledge bootstrap**: Run `/knowledge-bootstrap {family} {platform}` for each platform
   in the family and check status:
   - `STOP:partial` → halt (see printed message)
   - Any other status (`READY`, `BOOTSTRAPPED`, `REFRESHED`, `WARN:conflicts`) → continue
2. Family page must exist at `content/products.aspose.org/en/{family}/_index.md` with `layout: family`.
   If missing, it is a structural page that must be created manually — `/new-products-page` creates
   platform product pages (`layout: plugin`), not family pages. Use the existing family page from
   another product as a template, stripping platform-specific content.
3. At least 1 platform subdirectory with `_index.md` (layout: plugin) must exist
4. Each platform should have merged knowledge at `knowledge/{family}/{platform}/merged/`

## Steps

> **Skill context gate** — run before step 1:
> ```bash
> PYTHONPATH=scripts/pipeline .venv/Scripts/python scripts/pipeline/commands/governance/skill_context.py begin --skill S-48 --scope "*"
> ```


1. **Discover platforms** — scan family directory for platform subdirs with plugin pages and knowledge
2. **Build platform list** — .NET first if present, then alphabetical; Oxford comma formatting
3. **Compute unified features** — aggregate feature claims across platforms; shared (all) vs partial (>=50%); exclude limitations
4. **Read existing family page** — preserve all fields NOT being rewritten
5. **Rewrite** `head_description`, `description`, `overview.content` using shared claims and platform list
6. **No-downgrade guard** — invoke before write; halt on BLOCK
7. **Write** updated `_index.md` — use read-modify-write via `yaml.safe_load` + `yaml.dump`; wrap `overview.content` in a `_Literal` helper before serializing so `yaml.dump` emits it as a `|` block scalar; reconstruct as `"---\n{serialized_fm}---\n\n{body}"` ending with `\n`; never prepend a new FM block to the existing file (causes double frontmatter); verify single FM block after write
8. **Attach evidence** — `python scripts/pipeline/commands/healing/attach_evidence.py --files {path}`
9. **Audit** — `python scripts/pipeline/commands/content/audit.py --files {path}` — must exit 0 FAIL

> **Skill context close** — run after the last step:
> ```bash
> PYTHONPATH=scripts/pipeline .venv/Scripts/python scripts/pipeline/commands/governance/skill_context.py end --skill S-48 --status completed
> ```

## Hard Constraints

- All claims from knowledge `claims.json` only — no fabrication
- No format claims unless confirmed in `formats.json` OR in `enriched_claims.json` feature/format claims
- No limitation denials
- Overview must NOT name individual platforms — describes the suite generically
- .NET always first in platform list
- Idempotent — running twice produces same result

## Integration

- Standalone: `/family-sync {family}`
- From `launch-product`: Stage 1.5 — after products page, when family has >= 2 platforms
