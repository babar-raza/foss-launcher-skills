# S-76: New Reference Index — Scaffold Reference Platform Section Landing Page

Scaffold or repair the reference platform `_index.md` section landing page.

**Arguments:** `$ARGUMENTS`
**Expected format:** `{family} {platform}` — e.g. `email cpp` or `slides java`

## Purpose

Creates the Hugo section landing page at
`$CONTENT_REPO_PATH/content/reference.aspose.org/en/{family}/{platform}/_index.md` with all required frontmatter
fields and the `{{< children >}}` shortcode. Without this file the reference section will fail to list classes or render incorrectly.

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
   - `version` — for the version string
   - `package_name` or `name` — for the product title
   - Top-level capability summary — for the description's format/operation list

4. **Check idempotency**: If the `_index.md` already exists AND contains `layout: list` AND
   contains `{{< children >}}` in the body, print `SKIP: _index.md already complete` and stop.

5. **Ensure family index exists**: Check if `$CONTENT_REPO_PATH/content/reference.aspose.org/en/{family}/_index.md` exists.
   If missing, create it with `layout: wide` and `{{< sections cols="4" >}}` shortcode.

6. **Derive values**:
   - `{Platform display}` — from the Platform Display Names table
   - `{weight}` — from the Platform Weights table
   - `{version}` — from `model.yaml`
   - `{description}` — `"Complete API reference for Aspose.{Family} FOSS for {Platform display} (v{version}). All public classes, methods, and enumerations for {2–4 key formats/operations}."`
   - `{summary}` — `"Public API reference for Aspose.{Family} FOSS for {Platform display} v{version}"`
   - `{body_intro}` — `"Browse all public types in **Aspose.{Family} FOSS for {Platform display}** v{version} — classes, enums, and interfaces covering {same 2–4 formats/operations}."`

7. **Pre-write quality check**: Invoke `no-downgrade-guard` (S-56) before writing.
   - If BLOCK → do not write; report the blocking reason
   - If WARN → present warning; await confirmation

8. **Write** `$CONTENT_REPO_PATH/content/reference.aspose.org/en/{family}/{platform}/_index.md`:

   ```markdown
   ---
   linkTitle: {Platform display}
   title: Aspose.{Family} FOSS for {Platform display}
   weight: {weight from step 6}
   description: "{description from step 6}"
   summary: "{summary from step 6}"
   layout: list
   categories:
   - API Reference
   provenance:
     content_origin: unknown
     last_mechanism: skill
     auto_updatable: false
     provenance_recovery_note: structural-page
   ---

   {body_intro from step 6}

   {{< children >}}
   ```

9. **Attach evidence**:
   ```bash
   python scripts/pipeline/commands/content/attach_evidence.py \
     --files $CONTENT_REPO_PATH/content/reference.aspose.org/en/{family}/{platform}/_index.md
   ```

10. **Run audit**:
    ```bash
    python scripts/pipeline/commands/content/audit.py \
      --files $CONTENT_REPO_PATH/content/reference.aspose.org/en/{family}/{platform}/_index.md
    ```
    Must exit with 0 FAIL before confirming success.

11. **Confirm** by printing the output file path and the values used for `linkTitle`, `weight`,
    `version`, and the first line of the body.
