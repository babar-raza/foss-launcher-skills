<!-- CONTRACT: scripts/pipeline/audit.py (invoked in Step 3)
     postcondition: audit.py returns automated structural PASS/WARN/FAIL report
     postcondition: agent performs knowledge cross-reference and evidence checks manually
     postcondition: skill is read-only — no file modifications
     verified: 2026-04-01
-->
# S-23: Content Check — Structural Quality Pre-Commit Check

Run a structural and quality check on a content file before committing.

**Arguments:** `$ARGUMENTS`
**Expected format:** `{relative-file-path}` — e.g. `content/kb.aspose.org/en/3d/python/how-to-load-models.md`

## Pre-conditions

1. **Knowledge bootstrap**: Run `/knowledge-bootstrap {family} {platform}` (detect `{family}` and `{platform}` from the file path argument) and check status:
   - `STOP:partial` → halt (see printed message)
   - Any other status (`READY`, `BOOTSTRAPPED`, `REFRESHED`, `WARN:conflicts`) → continue

## Steps

1. **Read the file** at the path given in `$ARGUMENTS`.

2. **Detect page type** from the path and frontmatter:
   - `content/kb.aspose.org/` → KB article (how-to or faq)
   - `content/docs.aspose.org/` → Docs page
   - `content/blog.aspose.org/` → Blog post
   - `content/reference.aspose.org/` → Reference page
   - `content/products.aspose.org/` → Product page

3. **Run automated structural checks via audit.py**:
   ```bash
   python scripts/pipeline/audit.py --files {relative-file-path}
   ```
   `audit.py` performs automated structural and schema checks and outputs a PASS/WARN/FAIL
   report. Read the script output and incorporate the results into the overall check.

   Then **perform the additional checks below** (these require agent reasoning and are not
   automated by the script):

   Record PASS / WARN / FAIL for each:

   ### Frontmatter checks (FAIL if any fail)
   - [ ] Frontmatter is valid YAML (no parse errors)
   - [ ] `title` field present and non-empty
   - [ ] `description` field present and non-empty
   - [ ] `draft` is `false` (WARN if `true` — not a blocker but flag it)
   - [ ] Date fields (`date`, `lastmod`) use `YYYY-MM-DD` format with quotes: `'2026-01-15'`
   - [ ] KB articles: `type: topic` present
   - [ ] Docs pages: `type: docs` present
   - [ ] Blog posts: `author: Aspose` and `categories` array present
   - [ ] Reference pages: `layout: reference-single` present
   - [ ] KB/blog: `keywords` list present with at least 5 items

   ### Content structure checks (FAIL if any fail)
   - [ ] File is not empty beyond frontmatter
   - [ ] No placeholder text remains (e.g. `{TODO}`, `TBD`, `PLACEHOLDER`, `Lorem ipsum`)
   - [ ] No broken internal links (links starting with `/kb.aspose.org/`, `/docs.aspose.org/`, `/reference.aspose.org/`, `/blog.aspose.org/`, `/products.aspose.org/` — check these paths exist in `content/`)
   - [ ] KB how-to: `{{% steps %}}` and `{{% /steps %}}` both present
   - [ ] KB how-to: at least 3 `### Step N:` headings present
   - [ ] Reference pages: Properties table present (at least one `|` table)

   ### Code quality checks (WARN if any fail)
   - [ ] All code blocks have a language identifier (` ```python `, ` ```bash `, etc.) — scan for bare ` ``` ` with no identifier
   - [ ] No class names or method names that do not appear in any reference content (cross-check against `content/reference.aspose.org/en/{family}/{platform}/` files if the family/platform is determinable from the file path)
   - [ ] `---` dividers present between major sections (WARN if fewer than 2)

   ### File path checks (FAIL if any fail)
   - [ ] File is under `content/` — not in a forbidden path (`themes/`, `layouts/`, `configs/`)
   - [ ] Filename uses kebab-case (all lowercase, hyphens, no spaces or underscores)
   - [ ] Blog posts: file is named `index.md` inside a slug directory, not a flat `.md` file

4. **Output a report** in this format:

   ```
   CONTENT CHECK — {file-path}
   Page type: {detected type}

   FRONTMATTER
     [PASS/WARN/FAIL] {check description}
     ...

   CONTENT STRUCTURE
     [PASS/WARN/FAIL] {check description}
     ...

   CODE QUALITY
     [PASS/WARN/FAIL] {check description}
     ...

   FILE PATH
     [PASS/WARN/FAIL] {check description}
     ...

   SUMMARY
   FAIL count: N   WARN count: N   PASS count: N
   OVERALL: PASS | WARN | FAIL
   ```

   OVERALL is FAIL if any individual check is FAIL. OVERALL is WARN if no FAIL but at least one WARN. OVERALL is PASS if all checks pass.

   ### Knowledge cross-reference checks (FAIL if any fail)
   - [ ] Detect `{family}` and `{platform}` from the file path
   - [ ] If `knowledge/{family}/{platform}/merged/index.json` exists, load it and run these checks:
     - [ ] Every class name mentioned in code blocks exists in `index.json` → `classes` array — FAIL if unknown class referenced
     - [ ] Every method call `ClassName.method()` in code blocks exists in `api_surface.json` — FAIL if unknown method
     - [ ] No paragraph semantically matches any entry in `index.json` → `forbidden_claims` — FAIL if forbidden claim detected
     - [ ] Format claims (e.g. "supports FBX export") are consistent with `index.json` → `formats` — FAIL if contradicted
     - [ ] `index.json` → `stale` is `false` — FAIL if knowledge is stale (run `/knowledge-diff` first)
     - [ ] Constructor calls `new ClassName(args)` in code blocks match constructor signatures in `api_surface.json` (methods where name is `<init>` or the class name) — FAIL if constructor signature doesn't exist
     - [ ] Every `import {pkg}` or `from {pkg}` statement in code blocks uses a package name that appears in `api_surface.json` file paths (e.g. `aspose/slides_foss/` → valid import is `aspose.slides_foss`) — FAIL if unknown package
     - [ ] Every `EnumName.MEMBER` reference in code blocks exists in `api_surface.json` enum definitions — FAIL if enum member not found (e.g. `ShapeType.ROUNDED_RECTANGLE` when only `ROUND_CORNER_RECTANGLE` exists)
     - [ ] Every property access `obj.property_name` in code blocks should be validated: if the object's class can be inferred from context, check that `property_name` exists on that class in `api_surface.json` — WARN if property not found (type inference is best-effort)
   - [ ] If `knowledge/{family}/{platform}/merged/index.json` does NOT exist: WARN "No knowledge model found — content cannot be verified against repo truth"

   ### Evidence frontmatter checks (WARN unless noted)
   - [ ] Frontmatter has an `evidence:` block with non-empty `model_sha` — WARN if missing or empty
   - [ ] `evidence.claims` array is non-empty — WARN if empty (page has no grounded claims)
   - [ ] All claim IDs in `evidence.claims` exist in `knowledge/{family}/{platform}/merged/claims.json` — WARN if any orphaned claim ID found
   - [ ] `evidence.apis` array is non-empty for pages with code blocks — WARN if empty
   - [ ] No `<!-- evidence: ... -->` HTML comment blocks in the page body — FAIL if found (violates AGENTS.md §5)

5. **If OVERALL is FAIL**: list each failing check with a one-line fix suggestion.

6. **Do not modify the file** — this skill is read-only.
