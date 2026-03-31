---
name: family-sync
description: >
  Update family-level products page to reflect all launched platforms
args: "{family}"
---

> Cross-skill references like `/knowledge-bootstrap` refer to sibling skills in this directory.

# S-48: Family Sync — Update Family Page for All Launched Platforms

**Arguments**: $ARGUMENTS
**Expected format**: `{family}` — e.g. `email` or `3d`

## Purpose

When a new platform is launched under an existing family, the family-level `_index.md` at
`content/products.aspose.org/en/{family}/_index.md` may contain hardcoded single-platform
prose in its `head_description`, `description`, and `overview.content` fields. This skill
discovers all launched platforms, reads their knowledge models, computes a unified capability
summary, and rewrites those three fields to be accurate and platform-inclusive.

The Hugo family layout already renders platform cards dynamically — this skill only touches
the **static text fields** in the frontmatter.

## Pre-conditions

1. Family page must exist at `content/products.aspose.org/en/{family}/_index.md`
   with `layout: family`.
   If missing: `STOP: No family page found. Run /new-products-page {family} --layout family first.`

2. At least 1 platform subdirectory must exist under
   `content/products.aspose.org/en/{family}/` containing an `_index.md` with `layout: plugin`.

3. Each launched platform should have merged knowledge at
   `knowledge/{family}/{platform}/merged/`. Platforms without knowledge are excluded from
   the sync with a printed `WARN`.

## Steps

### Step 1: Discover launched platforms

Scan `content/products.aspose.org/en/{family}/` for subdirectories containing `_index.md`.

For each discovered platform directory:
- Verify `_index.md` has `layout: plugin` in its frontmatter
- Check `knowledge/{family}/{platform}/merged/` exists:
  - If missing: `WARN: No knowledge for {platform}, excluding from sync.` — skip this platform
- Load knowledge artifacts:
  - `knowledge/{family}/{platform}/merged/claims.json` — filter to `kind: "feature"` with `confidence >= 0.7`
  - `knowledge/{family}/{platform}/merged/formats.json` — supported file formats
  - `knowledge/{family}/{platform}/merged/limitations.md` — excluded capabilities
  - `knowledge/{family}/{platform}/scout/model.yaml` — `product_name`, `version`
- Read platform `_index.md` frontmatter for `plugin_platform` display name

Store as `platforms[]` list.

If 0 platforms have knowledge: `STOP: No platforms with knowledge found — nothing to sync.`

### Step 2: Build platform list string

Map folder names to display names using `plugin_platform` from each platform's `_index.md`:
- `net` -> `.NET`
- `python` -> `Python`
- `java` -> `Java`
- `cpp` -> `C++`
- `typescript` -> `TypeScript`

Ordering rule: **.NET first** if present, then remaining platforms in **alphabetical order**
by display name.

Format as Oxford-comma English list:
- 1 platform: `"Python"`
- 2 platforms: `".NET and Python"`
- 3 platforms: `".NET, C++, and Python"`
- 4+ platforms: `".NET, Java, Python, and TypeScript"`

Store as `platform_list_str`.

### Step 3: Compute unified feature summary

1. Collect all claims with `kind: "feature"` and `confidence >= 0.7` from every platform's
   `claims.json`
2. Classify each capability by platform coverage:
   - **Shared** — present in ALL platforms (primary content for family text)
   - **Majority** — present in >= 50% of platforms (may be mentioned with qualifier)
   - **Partial** — present in < 50% (excluded from family text)
3. For shared claims, pick the claim text with highest `confidence` as representative
4. Collect the union of supported formats from all `formats.json` files; identify which
   formats are universal (all platforms) vs partial
5. Cross-check against each platform's `limitations.md` — never present a limited
   capability as working

If fewer than 3 shared feature claims exist:
`WARN: Very few shared capabilities across platforms. Family page overview will be generic.`

### Step 4: Read existing family page

Read `content/products.aspose.org/en/{family}/_index.md` and parse YAML frontmatter.

Preserve ALL fields that are NOT being rewritten:
- `layout`, `type`, `button`, `testimonialswrapper`, `support`, `back_to_top` — preserved exactly
- `head_title` — preserved (product name does not change)
- `evidence` — will be refreshed in Step 8

Only these three fields are rewritten:
- `head_description`
- `description`
- `overview.content`

### Step 5: Rewrite target fields

**`head_description`** (max ~160 characters):

Template: `"{ProductName} FOSS is a free, open-source library for {core_capability_phrase}. MIT licensed. Available for {platform_list_str}."`

Where `core_capability_phrase` is derived from the highest-confidence shared feature claims
(max 15 words, describing what the library does). Must NOT name individual platforms.

**`description`**:

Template: `"{core_action_phrase} — free and open-source, available for {platform_list_str}."`

Where `core_action_phrase` is an imperative-mood summary (e.g., "Read, create, and process
Outlook MSG files, CFB containers, and EML messages") derived from shared feature claims.

**`overview.content`** (pipe-style `|` block scalar):

Single paragraph that:
1. Opens with suite framing:
   - If >= 2 platforms: `"{ProductName} FOSS is a suite of free, MIT-licensed open-source libraries for {capability_summary}"`
   - If 1 platform: `"{ProductName} FOSS is a free, MIT-licensed open-source library for {capability_summary}"`
2. Describes shared capabilities using only verified claims — mentions universal formats
   by name if applicable
3. Closes with: `"Every library in the suite installs with a single package manager command and runs identically on Windows, macOS, Linux, Docker, and serverless."` (adjust "suite" to singular if 1 platform)

All capability claims used MUST be traceable to claims in at least one platform's `claims.json`.

### Step 6: No-downgrade guard

Invoke `no-downgrade-guard` with the target path and proposed content:
- **BLOCK** -> halt; report reason to user
- **WARN** -> print warning; require user confirmation before proceeding
- **ALLOW** -> continue to write

### Step 7: Write updated family page

Write the updated `_index.md` using the following **exact reconstruction protocol** to
prevent double-frontmatter corruption:

1. Parse the existing file's frontmatter with `yaml.safe_load` into a dict.
2. Update only `head_description`, `description`, and `overview.content` in the dict.
3. Serialize the full updated dict back with `yaml.dump(..., default_flow_style=False, allow_unicode=True, sort_keys=False)`.
4. Reconstruct the file as `f"---\n{serialized_fm}---\n\n{body}"` where `body` is the
   original body content after the closing `---` fence.
5. The reconstructed string **must end with `\n`**. If the body is empty, use
   `f"---\n{serialized_fm}---\n"`.
6. **Never** prepend a new `---...---` block to the existing file content — always
   replace the whole frontmatter block in one atomic write.

After writing, verify no double frontmatter was introduced:

```bash
python -c "
import re, sys
path = 'content/products.aspose.org/en/{family}/_index.md'
text = open(path, encoding='utf-8').read()
blocks = re.findall(r'^---\s*\n.*?\n---\s*(?:\n|$)', text, re.DOTALL)
if len(blocks) > 1:
    print(f'ERROR: double frontmatter in {path}')
    sys.exit(1)
print('OK: single frontmatter block')
"
```

If this check fails, do not proceed — fix the file before continuing.

### Step 8: Attach evidence

```bash
python scripts/pipeline/attach_evidence.py --files content/products.aspose.org/en/{family}/_index.md
```

### Step 9: Run audit

```bash
python scripts/pipeline/audit.py --files content/products.aspose.org/en/{family}/_index.md
```

Must exit with 0 FAIL. If FAIL count > 0, fix the issues and re-run.

## Post-conditions

- `head_description` contains ALL launched platform display names
- `description` contains ALL launched platform display names
- `overview.content` is platform-agnostic (describes the suite, not one platform)
- No platform with knowledge is omitted from platform list strings
- Platform list follows ordering rule (.NET first, then alphabetical)
- All capability claims in rewritten text are grounded in at least one platform's knowledge
- No claims from any platform's `limitations.md` are presented as working features
- `evidence:` frontmatter block refreshed by `attach_evidence.py`
- `audit.py` exits with 0 FAIL
- `layout: family` is preserved
- All non-target frontmatter fields are unchanged

## Hard Constraints

- **Preserve non-target fields** — never remove or modify fields that are not `head_description`,
  `description`, or `overview.content` (e.g., `testimonialswrapper`, `support`, `back_to_top`)
- **No fabrication** — all capability claims must come from knowledge `claims.json`
- **No unsupported formats** — never reference a format unless it appears in `formats.json`
  for at least one platform
- **No limitation denials** — never claim a capability that is listed in any platform's
  `limitations.md` as unsupported
- **Platform display names** must use canonical values from each platform's `plugin_platform`
  frontmatter field
- **.NET always first** in platform list when present
- **Overview must NOT name individual platforms** — it describes the suite generically
- **Single-platform valid** — if only 1 platform, use "library" not "suite of libraries";
  the skill still produces correct output
- **`overview.content`** must remain a `|` block scalar in YAML (pipe-style multiline)
- **Idempotent** — running the skill twice with the same inputs produces the same result

## Integration

This skill is called:
1. **Standalone**: `/family-sync {family}` — any time a family page needs refreshing
2. **From `launch-product`**: Stage 1.5 — automatically after products page generation
   when the family has >= 2 launched platforms
