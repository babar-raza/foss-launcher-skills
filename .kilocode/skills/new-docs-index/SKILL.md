---
name: new-docs-index
description: >
  Scaffold or repair the docs platform `_index.md` section landing page.
args: "

## Purpose

Creates the Hugo section landing page at
"
---

> Cross-skill references like `/knowledge-bootstrap` refer to sibling skills in this directory.

# S-70: New Docs Index — Scaffold Docs Platform Section Landing Page

Scaffold or repair the docs platform `_index.md` section landing page.

**Arguments:** `$ARGUMENTS`
**Expected format:** `{family} {platform}` — e.g. `email cpp` or `slides java`

## Purpose

Creates the Hugo section landing page at
`content/docs.aspose.org/en/{family}/{platform}/_index.md` with all required frontmatter
fields and the `{{< sections >}}` shortcode. Without this file (or when it is missing
`linktitle`, `subtitle`, `icon`, `layout: list`, or the shortcode), the docs section may
render blank or fail to build.

## Platform Display Names

| platform key | display name |
|---|---|
| `net` | `.NET` |
| `java` | `Java` |
| `python` | `Python` |
| `cpp` | `C++` |
| `typescript` | `TypeScript` |
| `nodejs` | `Node.js` |
| `android` | `Android` |

For any unlisted platform key, capitalise the first letter.

## Platform Weights

| platform key | weight |
|---|---|
| `net` | 20 |
| `java` | 30 |
| `python` | 40 |
| `cpp` | 40 |
| `typescript` | 50 |
| `nodejs` | 60 |
| `android` | 70 |

Default weight for unlisted platforms: 80.

## Steps

1. **Parse** `$ARGUMENTS` into `family` and `platform`.

2. **Bootstrap knowledge**: Run `/knowledge-bootstrap {family} {platform}` and check status:
   - `KNOWLEDGE: STOP:partial` → halt; see printed message
   - `KNOWLEDGE: REFRESHED` → STOP: "Knowledge refreshed from upstream changes. Re-run this command."
   - Any other status → continue

3. **Read** `knowledge/{family}/{platform}/model.yaml` and extract:
   - `description` — for the body intro sentence
   - `version` — for version references if needed
   - `install_command` or `requirements` — for the platform requirement sentence

4. **Check idempotency**: If `content/docs.aspose.org/en/{family}/{platform}/_index.md` already
   exists AND contains `linktitle` in frontmatter AND contains `layout: list` in frontmatter AND contains `{{< sections >}}` in the body,
   print `SKIP: _index.md already complete` and stop — do not overwrite.

5. **Derive values**:
   - `{Platform display}` — from the Platform Display Names table above
   - `{weight}` — from the Platform Weights table above
   - `{description}` — `"{Platform display} documentation for Aspose.{Family} FOSS: {2–4 key
     action verbs describing what the library does, derived from model.yaml}"`
   - `{body_intro}` — one sentence describing the platform requirement for using the library:
     compiler/runtime version, install command, and whether there are external dependencies
     (e.g. "Requires a C++17 compiler. Include headers from `include/aspose/...` and link via
     CMake. No external dependencies." OR "Requires .NET 8.0 or later. Install with
     `dotnet add package {package_name}`. Pure managed code.")

6. **Pre-write quality check**: Invoke `no-downgrade-guard` before writing:
   - Target path: `content/docs.aspose.org/en/{family}/{platform}/_index.md`
   - If BLOCK → do not write; report the blocking reason
   - If WARN → present warning; await confirmation
   - If ALLOW → proceed

7. **Write** `content/docs.aspose.org/en/{family}/{platform}/_index.md` with this exact structure:

   ```
   ---
   title: Aspose.{Family} FOSS for {Platform display}
   linktitle: {Platform display}
   subtitle: Aspose.{Family} FOSS for {Platform display}
   description: "{description from step 5}"
   icon: terminal
   weight: {weight from step 5}
   layout: list
   provenance:
     content_origin: unknown
     last_mechanism: skill
     auto_updatable: false
     provenance_recovery_note: structural-page
     content_created_at: '{today as YYYY-MM-DD}'
   ---

   {body_intro from step 5}

   Select a section to begin:

   {{< sections >}}
   ```

   Note: the `evidence:` and `grade:` blocks are written by `attach_evidence.py` in the next
   step — do not add them manually. The `provenance:` block above is included in the template
   by design: structural index pages receive `content_origin: unknown` with `auto_updatable: false`
   at creation time (structural-deferred classification per Phase N provenance governance).

   Note: use `linktitle` (all lowercase) — this is the Hugo docs theme convention for this site,
   distinct from `linkTitle` (camelCase) used in the KB and reference sites.

8. **Attach evidence**: Run:
   ```bash
   .venv/Scripts/python scripts/pipeline/attach_evidence.py \
     --files content/docs.aspose.org/en/{family}/{platform}/_index.md
   ```

9. **Run audit**: Run:
   ```bash
   .venv/Scripts/python scripts/pipeline/audit.py \
     --files content/docs.aspose.org/en/{family}/{platform}/_index.md
   ```
   Must exit with 0 FAIL before confirming success.

10. **Confirm** by printing the output file path and the values used for `linktitle`, `weight`,
    and the first line of the body.
