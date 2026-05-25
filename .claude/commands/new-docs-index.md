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

> **Skill context gate** — run before step 1:
> ```bash
> PYTHONPATH=scripts/pipeline .venv/Scripts/python scripts/pipeline/commands/governance/skill_context.py begin --skill S-70 --scope "*"
> ```


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

5. **Ensure family index exists**: Check if `content/docs.aspose.org/en/{family}/_index.md` exists.
   If it already exists AND contains `subtitle:` in its frontmatter, skip to step 6. If it exists but lacks `subtitle:`, read `model.yaml`, derive a 5–8 word summary, add the `subtitle` field to the existing frontmatter (preserving all other fields), run `attach_evidence.py` and `audit.py` on the updated file (0 FAIL required), then continue to step 6. If missing, create it:

   a. Read `data/families_order.json` and find the 0-based index of `{family}`. Compute
      `weight = (index + 1) * 10`. If the family is not listed, use weight 100.

   b. Look up the family icon from this table:

      | Family | Icon |
      |--------|------|
      | words | `pencil-alt` |
      | cells | `table` |
      | email | `mail` |
      | slides | `presentation-chart-bar` |
      | note | `document-text` |
      | 3d | `cube` |
      | pdf | `document` |
      | *other* | `document` |

   c. Write `content/docs.aspose.org/en/{family}/_index.md`:

      ```
      ---
      title: Aspose.{Family} FOSS
      subtitle: {5–8 word summary from model.yaml description}
      description: "Aspose.{Family} FOSS documentation for {key verbs from model.yaml}."
      icon: {icon from table above}
      layout: wide
      weight: {weight from step 5a}
      provenance:
        content_origin: unknown
        last_mechanism: skill
        auto_updatable: false
        provenance_recovery_note: structural-page
      ---

      {1–2 sentence description from model.yaml}

      ## Key capabilities
      {3–6 bullet points derived from model.yaml and claims.json}

      Select your platform to access documentation:

      {{< sections cols="4" >}}
      ```

      > **IMPORTANT**: Do NOT add a `linkTitle` field to the family root `_index.md`.
      > The Hugo sidebar partial prioritizes `LinkTitle` over `Title`; adding
      > `linkTitle` causes the sidebar to show the short name instead of
      > "Aspose.{Family} FOSS". Only platform-level `_index.md` files (step 8)
      > use `linkTitle`. Enforced by: launch gate L-11.

   d. Run `attach_evidence.py` and `audit.py` on the new file (0 FAIL required).

6. **Derive values**:
   - `{Platform display}` — from the Platform Display Names table above
   - `{weight}` — from the Platform Weights table above
   - `{description}` — `"{Platform display} documentation for Aspose.{Family} FOSS: {2–4 key
     action verbs describing what the library does, derived from model.yaml}"`
   - `{body_intro}` — one sentence describing the platform requirement for using the library:
     compiler/runtime version, install command, and whether there are external dependencies
     (e.g. "Requires a C++17 compiler. Include headers from `include/aspose/...` and link via
     CMake. No external dependencies." OR "Requires .NET 8.0 or later. Install with
     `dotnet add package {package_name}`. Pure managed code.")

7. **Pre-write quality check**: Invoke `no-downgrade-guard` before writing:
   - Target path: `content/docs.aspose.org/en/{family}/{platform}/_index.md`
   - If BLOCK → do not write; report the blocking reason
   - If WARN → present warning; await confirmation
   - If ALLOW → proceed

8. **Write** `content/docs.aspose.org/en/{family}/{platform}/_index.md` with this exact structure:

   ```
   ---
   title: Aspose.{Family} FOSS for {Platform display}
   linktitle: {Platform display}
   subtitle: Aspose.{Family} FOSS for {Platform display}
   description: "{description from step 6}"
   icon: terminal
   weight: {weight from step 6}
   layout: list
   provenance:
     content_origin: unknown
     last_mechanism: skill
     auto_updatable: false
     provenance_recovery_note: structural-page
   ---

   {body_intro from step 6}

   Select a section to begin:

   {{< sections >}}
   ```

   Note: the `evidence:` and `grade:` blocks are written by `attach_evidence.py` in the next
   step — do not add them manually. The `provenance:` block above is included in the template
   by design: structural index pages receive `content_origin: unknown` with `auto_updatable: false`
   at creation time (structural-deferred classification per Phase N provenance governance).

   Note: use `linktitle` (all lowercase) — this is the Hugo docs theme convention for this site,
   distinct from `linkTitle` (camelCase) used in the KB and reference sites.

9. **Attach evidence**: Run:
   ```bash
   .venv/Scripts/python scripts/pipeline/commands/healing/attach_evidence.py \
     --files content/docs.aspose.org/en/{family}/{platform}/_index.md
   ```

10. **Run audit**: Run:
    ```bash
    .venv/Scripts/python scripts/pipeline/commands/content/audit.py \
      --files content/docs.aspose.org/en/{family}/{platform}/_index.md
    ```
    Must exit with 0 FAIL before confirming success.

11. **Confirm** by printing the output file path and the values used for `linktitle`, `weight`,
    and the first line of the body.

> **Skill context close** — run after the last step:
> ```bash
> PYTHONPATH=scripts/pipeline .venv/Scripts/python scripts/pipeline/commands/governance/skill_context.py end --skill S-70 --status completed
> ```

