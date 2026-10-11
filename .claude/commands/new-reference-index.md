# S-71: New Reference Index — Scaffold Reference Platform Section Landing Page

Scaffold or repair the reference platform `_index.md` section landing page.

**Arguments:** `$ARGUMENTS`
**Expected format:** `{family} {platform}` — e.g. `email cpp` or `slides java`

## Purpose

Creates the Hugo section landing page at
`content/reference.aspose.org/en/{family}/{platform}/_index.md` with all required frontmatter
fields and a grouped, per-module class table (Step 8 writes a temporary `{{< children >}}`
scaffold; Step 8b immediately regenerates it into grouped tables via
`batch_reference.py --generate-index` — see Step 8b). Without this file (or when it is missing
`layout: list`, `summary`, `categories`, or a grouped body), the reference section
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

> **Skill context gate** — run before step 1:
> ```bash
> PYTHONPATH=scripts/pipeline .venv/Scripts/python scripts/pipeline/commands/governance/skill_context.py begin --skill S-71 --scope "*"
> ```


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

5. **Ensure family index exists**: Check if `content/reference.aspose.org/en/{family}/_index.md` exists.
   If it already exists, skip to step 6. If missing, create it:

   a. Read `data/families_order.json` and find the 0-based index of `{family}`. Compute
      `weight = (index + 1) * 10`. If the family is not listed, use weight 100.

   b. Look up the family's canonical icon from `data/family_icons.yaml`. This is the
      single source of truth — do NOT use a hardcoded table. Read the file and find
      the entry for `{family}`. If no entry exists for this family, STOP and add one
      to `data/family_icons.yaml` first (choosing an unused icon), then proceed.

      To check available unused icons, run:
        python scripts/ci/checks/check_family_icon_uniqueness.py
      The output lists unused icons on any FAIL; on OK, all icons are assigned.

   c. Write `content/reference.aspose.org/en/{family}/_index.md`:

      ```
      ---
      title: Aspose.{Family} FOSS
      subtitle: {5–8 word summary from model.yaml description}
      description: "API reference for Aspose.{Family} FOSS: {top 3–4 class names} and all classes for {domain from model.yaml}."
      icon: {icon from data/family_icons.yaml for this family}
      layout: wide
      weight: {weight from step 5a}
      provenance:
        content_origin: unknown
        last_mechanism: skill
        auto_updatable: false
        provenance_recovery_note: structural-page
      ---

      Aspose.{Family} FOSS API reference for all supported platforms. Select your platform to browse classes, methods, and properties.

      {{< sections cols="4" >}}
      ```

      > **IMPORTANT**: Do NOT add a `linkTitle` field to the family root `_index.md`.
      > The Hugo sidebar partial (`themes/docs/layouts/partials/utils/title.html`)
      > prioritizes `LinkTitle` over `Title`. Adding `linkTitle` causes the sidebar
      > to display the short name (e.g., "Font") instead of "Aspose.{Family} FOSS".
      > Only platform-level `_index.md` files (step 8) use `linkTitle`.
      > Enforced by: `scripts/ci/checks/check_family_display_names.py`, launch gate L-11.

   d. Run `attach_evidence.py` and `audit.py` on the new file (0 FAIL required).

6. **Derive values**:
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

7. **Pre-write quality check**: Invoke `no-downgrade-guard` before writing:
   - Target path: `content/reference.aspose.org/en/{family}/{platform}/_index.md`
   - If BLOCK → do not write; report the blocking reason
   - If WARN → present warning; await confirmation
   - If ALLOW → proceed

8. **Write** `content/reference.aspose.org/en/{family}/{platform}/_index.md` with this exact
   structure:

   ```
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

   Note: the `evidence:` and `grade:` blocks are written by `attach_evidence.py` in the next
   step — do not add them manually. The `provenance:` block above is a **transient scaffold**,
   not the final state: it exists only to seed `linkTitle`/`weight`/`description`/`summary`/base
   provenance for Step 8b to read and rewrite. It must never survive to the committed page except
   in the genuine-skip case documented in Step 8b.

8b. **Generate the grouped index** (TC-REF-14, 2026-07-25): Immediately convert the Step 8
    scaffold into the required grouped-table structure — do NOT leave the bare `{{< children >}}`
    body in place. Run:
    ```bash
    PYTHONPATH=scripts/pipeline .venv/Scripts/python scripts/pipeline/commands/content/batch_reference.py \
      {family} {platform} --generate-index
    ```
    - **`SUCCESS: Grouped index written to ...`** → the flat scaffold body is replaced with
      `## Module` headings + `| Class | Description |` tables, and `provenance.auto_updatable`
      flips to `true` / `content_origin` to `skill-generated` / `provenance_recovery_note` is
      dropped. Continue to Step 9 as normal.
    - **`SKIPPED: api_surface.json missing`** or **`SKIPPED: ... too small (<5 entries)`** →
      knowledge for this platform is too thin to group (e.g. scout-only/degraded enrichment).
      The Step 8 flat scaffold legitimately persists — but this is NOT a silent allowed state:
      file a backlog follow-up (same pattern as `RUST-ENRICH-001`) noting the platform needs a
      knowledge re-enrichment pass and an `S-84 refresh-product` (or direct `--generate-index`)
      follow-up once knowledge improves. Do not confirm the skill run as fully complete without
      this follow-up filed.

    Background: a one-off manual heal (commit `b8dced9004`, 2026-05-25) migrated 10 platforms
    from this flat scaffold to grouped tables using the same `generate_grouped_index()` function
    this step now calls, but the heal was never folded back into this skill — every platform
    launched via Step 8 alone between 2026-05-25 and 2026-07-25 (`words/net`, `cells/rust`,
    `html/python`) silently regressed to the pre-heal flat structure. Step 8b closes that gap.

9. **Attach evidence**: Run:
   ```bash
   .venv/Scripts/python scripts/pipeline/commands/healing/attach_evidence.py \
     --files content/reference.aspose.org/en/{family}/{platform}/_index.md
   ```

10. **Run audit**: Run:
    ```bash
    .venv/Scripts/python scripts/pipeline/commands/content/audit.py \
      --files content/reference.aspose.org/en/{family}/{platform}/_index.md
    ```
    Must exit with 0 FAIL before confirming success.

11. **Confirm** by printing the output file path and the values used for `linkTitle`, `weight`,
    `version`, and the first line of the body.

> **Skill context close** — run after the last step:
> ```bash
> PYTHONPATH=scripts/pipeline .venv/Scripts/python scripts/pipeline/commands/governance/skill_context.py end --skill S-71 --status completed
> ```

