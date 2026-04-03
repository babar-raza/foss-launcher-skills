# S-71: New Reference Index — Scaffold Reference Platform Section Landing Page

Scaffold or repair the reference platform `_index.md` section landing page.

**Arguments:** `$ARGUMENTS`
**Expected format:** `{family} {platform}` — e.g. `email cpp` or `slides java`

## Purpose

Creates the Hugo section landing page at
`content/reference.aspose.org/en/{family}/{platform}/_index.md` with all required frontmatter
fields and the `{{< children >}}` shortcode. Without this file (or when it is missing
`layout: list`, `summary`, `categories`, or the shortcode), the reference section
will fail to list classes or render incorrectly.

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
   - `version` — for the version string in description and summary
   - `package_name` or `name` — for the product title
   - `formats` or top-level capability summary — for the description's format/operation list

4. **Check idempotency**: If `content/reference.aspose.org/en/{family}/{platform}/_index.md`
   already exists AND contains `layout: list` in frontmatter AND contains
   `{{< children >}}` in the body, print `SKIP: _index.md already complete` and stop.

5. **Derive values**:
   - `{Platform display}` — from the Platform Display Names table above
   - `{weight}` — from the Platform Weights table above
   - `{version}` — from `model.yaml`
   - `{description}` — `"Complete API reference for Aspose.{Family} FOSS for {Platform display}
     (v{version}). All public classes, methods, and enumerations for {2–4 key formats/operations
     from model.yaml — e.g. 'MSG, CFB, and EML operations'}."`
   - `{summary}` — `"Public API reference for Aspose.{Family} FOSS for {Platform display}
     v{version}"`
   - `{body_intro}` — `"Browse all public types in **Aspose.{Family} FOSS for {Platform display}**
     v{version} — classes, enums, and interfaces covering {same 2–4 formats/operations as
     description}."`

6. **Pre-write quality check**: Invoke `no-downgrade-guard` before writing:
   - Target path: `content/reference.aspose.org/en/{family}/{platform}/_index.md`
   - If BLOCK → do not write; report the blocking reason
   - If WARN → present warning; await confirmation
   - If ALLOW → proceed

7. **Write** `content/reference.aspose.org/en/{family}/{platform}/_index.md` with this exact
   structure:

   ```
   ---
   linkTitle: {Platform display}
   title: Aspose.{Family} FOSS for {Platform display}
   weight: {weight from step 5}
   description: "{description from step 5}"
   summary: "{summary from step 5}"
   layout: list
   categories:
   - API Reference
   ---

   {body_intro from step 5}

   {{< children >}}
   ```

   Note: the `evidence:`, `grade:`, and `provenance:` blocks are written by `attach_evidence.py`
   in the next step — do not include them manually.

8. **Attach evidence**: Run:
   ```bash
   .venv/Scripts/python scripts/pipeline/attach_evidence.py \
     --files content/reference.aspose.org/en/{family}/{platform}/_index.md
   ```

9. **Run audit**: Run:
   ```bash
   .venv/Scripts/python scripts/pipeline/audit.py \
     --files content/reference.aspose.org/en/{family}/{platform}/_index.md
   ```
   Must exit with 0 FAIL before confirming success.

10. **Confirm** by printing the output file path and the values used for `linkTitle`, `weight`,
    `version`, and the first line of the body.
