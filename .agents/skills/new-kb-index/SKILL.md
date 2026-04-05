---
name: new-kb-index
description: >
  Scaffold or repair the KB platform `_index.md` section landing page.
args: "

## Purpose

Creates the Hugo section landing page at "
---

> Cross-skill references like `/knowledge-bootstrap` refer to sibling skills in this directory.

# S-69: New KB Index — Scaffold KB Platform Section Landing Page

Scaffold or repair the KB platform `_index.md` section landing page.

**Arguments:** `$ARGUMENTS`
**Expected format:** `{family} {platform}` — e.g. `email cpp` or `slides java`

## Purpose

Creates the Hugo section landing page at `content/kb.aspose.org/en/{family}/{platform}/_index.md`
with all required frontmatter fields and the `{{< children >}}` shortcode. Without this file
(or when it is missing `linkTitle`, `subtitle`, `icon`, `layout: list`, or the shortcode), the section renders
blank in Hugo.

## Platform Display Names

Use these canonical display names for `linkTitle`, `subtitle`, and `title`:

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
   - `description` field (1–2 sentences describing the library) for use in the body
   - `title` or `name` field for the human-readable family/product name

4. **Check idempotency**: If `content/kb.aspose.org/en/{family}/{platform}/_index.md` already
   exists AND contains `linkTitle` in frontmatter AND contains `layout: list` in frontmatter AND contains `{{< children >}}` in the body,
   print `SKIP: _index.md already complete` and stop — do not overwrite.

5. **Derive values**:
   - `{Platform display}` — from the Platform Display Names table above
   - `{weight}` — from the Platform Weights table above
   - `{description}` — `"{Platform display} how-to guides for Aspose.{Family} FOSS: {2–4 key
     action verbs from the library description, e.g. 'read, create, and convert MSG and EML
     files without Microsoft Outlook'}"`
   - `{body_intro}` — one sentence from `model.yaml` description that captures what the
     library is and its key strength (e.g. "Free, MIT-licensed C++ library for reading and
     writing email files without Microsoft Outlook.")

6. **Pre-write quality check**: Invoke `no-downgrade-guard` before writing:
   - Target path: `content/kb.aspose.org/en/{family}/{platform}/_index.md`
   - If BLOCK → do not write; report the blocking reason
   - If WARN → present warning; await confirmation
   - If ALLOW → proceed

7. **Write** `content/kb.aspose.org/en/{family}/{platform}/_index.md` with this exact structure:

   ```
   ---
   title: Aspose.{Family} FOSS for {Platform display}
   linkTitle: {Platform display}
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
   ---

   {body_intro from step 5}

   Browse how-to guides:

   {{< children >}}
   ```

   Note: the `evidence:` and `grade:` blocks are written by `attach_evidence.py` in the next
   step — do not add them manually. The `provenance:` block above is included in the template
   by design: structural index pages receive `content_origin: unknown` with `auto_updatable: false`
   at creation time (structural-deferred classification per Phase N provenance governance).

8. **Attach evidence**: Run:
   ```bash
   .venv/Scripts/python scripts/pipeline/attach_evidence.py \
     --files content/kb.aspose.org/en/{family}/{platform}/_index.md
   ```

9. **Run audit**: Run:
   ```bash
   .venv/Scripts/python scripts/pipeline/audit.py \
     --files content/kb.aspose.org/en/{family}/{platform}/_index.md
   ```
   Must exit with 0 FAIL before confirming success.

10. **Confirm** by printing the output file path and the values used for `linkTitle`, `weight`,
    and the first line of the body.
