# CLAUDE.md — Agent Ground Rules

Hugo multi-site monorepo for Aspose FOSS product documentation.

## Sites & Content Paths

| Site | Config | Content |
|------|--------|---------|
| docs.aspose.org | `configs/docs.aspose.org.toml` | `content/docs.aspose.org/en/{family}/{platform}/` |
| blog.aspose.org | `configs/blog.aspose.org.toml` | `content/blog.aspose.org/{family}/{platform}/` |
| kb.aspose.org | `configs/kb.aspose.org.toml` | `content/kb.aspose.org/en/{family}/{platform}/` |
| products.aspose.org | `configs/products.aspose.org.toml` | `content/products.aspose.org/en/{family}/` |
| reference.aspose.org | `configs/reference.aspose.org.toml` | `content/reference.aspose.org/en/{family}/{platform}/` |

## Critical Rules

1. **Read AGENTS.md first** — it is the authoritative governance file for all content work.
2. **Forbidden write paths** — never write to `themes/`, `layouts/`, `configs/`, `AGENTS.md`, or `CLAUDE.md` without explicit human override.
3. **Evidence-first** — every content edit must be grounded in the knowledge model (`knowledge/{family}/{platform}/`). Read `model.yaml` before touching any content page.
4. **Knowledge freshness** — if `model.yaml` has `stale_since != null`, stop and run the maintenance workflow (S-12 → S-14) before editing content.

## Do / Don't

- **Do** check `knowledge/` artifacts before writing any content
- **Do** include evidence citations in content pages
- **Do** run ground-check (S-23) before committing content changes
- **Don't** fabricate API names, format claims, or code snippets — all must come from knowledge files
- **Don't** skip the skill chain defined in AGENTS.md Section 6
- **Don't** commit content without the evidence proof required by AGENTS.md Section 10
