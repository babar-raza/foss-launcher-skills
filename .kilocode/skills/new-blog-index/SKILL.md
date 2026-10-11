---
name: new-blog-index
id: S-101
description: >
  Creates the Hugo branch bundle at
---

> Cross-skill references like `/knowledge-bootstrap` refer to sibling skills in this directory.

<!-- CONTRACT: agent-executed
     postcondition: content/blog.aspose.org/{family}/{platform}/_index.md exists with title frontmatter
     postcondition: Hugo can generate section index page for /{family}/{platform}/
     verified: 2026-05-20
     depends_on: []
-->
# S-101: New Blog Index — Scaffold Blog Platform Section Branch Bundle

Create or verify the blog platform `_index.md` branch bundle file.

**Arguments:** `$ARGUMENTS`
**Expected format:** `{family} {platform}` — e.g. `words python` or `slides java`

## Purpose

Creates the Hugo branch bundle at
`content/blog.aspose.org/{family}/{platform}/_index.md` with a title-only
frontmatter block. Without this file, Hugo does not generate section index
pages for nested sub-sections (depth >= 2), causing 404s on routes like
`/words/python/` or `/cells/java/`.

The blog section template (`layouts/_default/section.html`) handles all
rendering via `blog_family_routes.yaml` lookup and `.RegularPagesRecursive` —
the `_index.md` file only needs to exist as a branch bundle marker with a
meaningful title for the `<title>` tag.

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

## Steps

> **Skill context gate** — run before step 1:
> ```bash
> PYTHONPATH=scripts/pipeline .venv/Scripts/python scripts/pipeline/commands/governance/skill_context.py begin --skill S-101 --scope "content/blog.aspose.org/*"
> ```

1. **Parse** `$ARGUMENTS` into `family` and `platform`.

2. **Validate family**: Read `data/blog_family_routes.yaml`. Confirm the `family`
   key exists under `families:`. If not found, STOP with error:
   `"Family '{family}' not registered in blog_family_routes.yaml. Add it first."`

3. **Look up display name**: Extract `taxonomy_term` from
   `blog_family_routes.yaml` → `families.{family}.taxonomy_term` (e.g. "Aspose.Words").

4. **Verify platform directory exists**: Check that
   `content/blog.aspose.org/{family}/{platform}/` is a directory containing at
   least one subdirectory with an `index.md` file (i.e., at least one blog post).
   If the directory does not exist or has no posts, STOP with error:
   `"No blog posts found at content/blog.aspose.org/{family}/{platform}/. Create posts first."`

5. **Check idempotency**: If `content/blog.aspose.org/{family}/{platform}/_index.md`
   already exists AND contains `title:` in its frontmatter, print
   `SKIP: _index.md already complete` and stop — do not overwrite.

6. **Determine platform display name** from the table above.

7. **Write** `content/blog.aspose.org/{family}/{platform}/_index.md`:

   ```
   ---
   title: "{taxonomy_term} for {Platform display}"
   ---
   ```

   No `evidence:`, `provenance:`, or `grade:` blocks — this is a structural
   branch bundle with no meaningful content body.

8. **Confirm** by printing the output file path and the title used.

> **Skill context close** — run after the last step:
> ```bash
> PYTHONPATH=scripts/pipeline .venv/Scripts/python scripts/pipeline/commands/governance/skill_context.py end --skill S-101 --status completed
> ```
