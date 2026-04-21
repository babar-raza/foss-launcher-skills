---
name: new-docs-index
id: S-75
description: >
  Scaffold or repair the docs platform section landing page at
  content/docs.aspose.org/en/{family}/{platform}/_index.md with required
  frontmatter fields and the sections shortcode.
args: "{family} {platform}"
---

# S-75: New Docs Index — Scaffold Docs Platform Section Landing Page

Scaffold or repair the docs platform `_index.md` section landing page.

**Arguments:** `$ARGUMENTS`
**Expected format:** `{family} {platform}` — e.g. `email cpp` or `slides java`

## Purpose

Creates the Hugo section landing page at
`$CONTENT_REPO_PATH/content/docs.aspose.org/en/{family}/{platform}/_index.md` with all required frontmatter
fields and the `{{< sections >}}` shortcode. Without this file the docs section may render blank or fail to build.

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
   - `version` — for version references
   - `install_command` or `requirements` — for the platform requirement sentence

4. **Check idempotency**: If the `_index.md` already exists AND contains `linktitle` in frontmatter
   AND contains `layout: list` AND contains `{{< sections >}}` in the body,
   print `SKIP: _index.md already complete` and stop.

5. **Ensure family index exists**: Check if `$CONTENT_REPO_PATH/content/docs.aspose.org/en/{family}/_index.md` exists.
   If missing, create it with `layout: wide` and `{{< sections >}}` shortcode.

6. **Derive values**:
   - `{Platform display}` — from the Platform Display Names table
   - `{weight}` — from the Platform Weights table
   - `{description}` — `"{Platform display} documentation for Aspose.{Family} FOSS: {2–4 key action verbs}"`
   - `{body_intro}` — one sentence describing the platform requirement for using the library

7. **Pre-write quality check**: Invoke `no-downgrade-guard` (S-56) before writing.
   - If BLOCK → do not write; report the blocking reason
   - If WARN → present warning; await confirmation

8. **Write** `$CONTENT_REPO_PATH/content/docs.aspose.org/en/{family}/{platform}/_index.md`:

   ```markdown
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

   Note: use `linktitle` (all lowercase) — Hugo docs theme convention, distinct from `linkTitle` (camelCase) used in the KB site.

9. **Attach evidence**:
   ```bash
   python scripts/pipeline/attach_evidence.py \
     --files $CONTENT_REPO_PATH/content/docs.aspose.org/en/{family}/{platform}/_index.md
   ```

10. **Run audit**:
    ```bash
    python scripts/pipeline/audit.py \
      --files $CONTENT_REPO_PATH/content/docs.aspose.org/en/{family}/{platform}/_index.md
    ```
    Must exit with 0 FAIL before confirming success.

11. **Confirm** by printing the output file path and the values used for `linktitle`, `weight`,
    and the first line of the body.
