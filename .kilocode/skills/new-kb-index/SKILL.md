---
name: new-kb-index
id: S-74
description: >
  Scaffold or repair the KB platform section landing page at
  content/kb.aspose.org/en/{family}/{platform}/_index.md with required
  frontmatter fields and the children shortcode.
args: "{family} {platform}"
---

# S-74: New KB Index — Scaffold KB Platform Section Landing Page

Scaffold or repair the KB platform `_index.md` section landing page.

**Arguments:** `$ARGUMENTS`
**Expected format:** `{family} {platform}` — e.g. `email cpp` or `slides java`

## Purpose

Creates the Hugo section landing page at `$CONTENT_REPO_PATH/content/kb.aspose.org/en/{family}/{platform}/_index.md`
with all required frontmatter fields and the `{{< children >}}` shortcode. Without this file
(or when it is missing `linkTitle`, `subtitle`, `icon`, `layout: list`, or the shortcode), the section renders blank.

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
| `net` | 10 |
| `java` | 20 |
| `python` | 30 |
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
   - `description` field for use in the body
   - `title` or `name` field for the human-readable family/product name

4. **Check idempotency**: If the `_index.md` already exists AND contains `linkTitle` in frontmatter
   AND contains `layout: list` AND contains `{{< children >}}` in the body,
   print `SKIP: _index.md already complete` and stop.

5. **Ensure family index exists**: Check if `$CONTENT_REPO_PATH/content/kb.aspose.org/en/{family}/_index.md` exists.
   If missing, create it with `layout: wide` and `{{< sections cols="4" >}}` shortcode.

6. **Derive values**:
   - `{Platform display}` — from the Platform Display Names table
   - `{weight}` — from the Platform Weights table
   - `{description}` — `"{Platform display} how-to guides for Aspose.{Family} FOSS: {2–4 key action verbs}"`
   - `{body_intro}` — one sentence from `model.yaml` description

7. **Pre-write quality check**: Invoke `no-downgrade-guard` (S-56) before writing.
   - If BLOCK → do not write; report the blocking reason
   - If WARN → present warning; await confirmation

8. **Write** `$CONTENT_REPO_PATH/content/kb.aspose.org/en/{family}/{platform}/_index.md`:

   ```markdown
   ---
   title: Aspose.{Family} FOSS for {Platform display}
   linkTitle: {Platform display}
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

   Browse how-to guides:

   {{< children >}}
   ```

9. **Attach evidence**:
   ```bash
   python scripts/pipeline/commands/content/attach_evidence.py \
     --files $CONTENT_REPO_PATH/content/kb.aspose.org/en/{family}/{platform}/_index.md
   ```

10. **Run audit**:
    ```bash
    python scripts/pipeline/commands/content/audit.py \
      --files $CONTENT_REPO_PATH/content/kb.aspose.org/en/{family}/{platform}/_index.md
    ```
    Must exit with 0 FAIL before confirming success.

11. **Confirm** by printing the output file path and the values used for `linkTitle`, `weight`,
    and the first line of the body.
