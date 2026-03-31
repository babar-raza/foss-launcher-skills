# CLAUDE.md — Agent Ground Rules

Standalone skills repo for Aspose FOSS product documentation generation and maintenance.
Skills operate against an external content repo configured via `$CONTENT_REPO_PATH`.

## Setup

Set the content repo path before running content-writing skills:
```bash
export CONTENT_REPO_PATH=/path/to/your/content-repo
# Or set content_root in config.yaml
```

## Sites & Content Paths (relative to `$CONTENT_REPO_PATH`)

| Site | Content path |
|------|-------------|
| docs.aspose.org | `content/docs.aspose.org/en/{family}/{platform}/` |
| blog.aspose.org | `content/blog.aspose.org/{family}/{platform}/` |
| kb.aspose.org | `content/kb.aspose.org/en/{family}/{platform}/` |
| products.aspose.org | `content/products.aspose.org/en/{family}/` |
| reference.aspose.org | `content/reference.aspose.org/en/{family}/{platform}/` |

## Critical Rules

1. **Read AGENTS.md first** — it is the authoritative governance file for all content work.
2. **Configure content root** — set `$CONTENT_REPO_PATH` or `config.yaml:content_root` before any content operation.
3. **Forbidden write paths** — never write to `themes/`, `layouts/`, `configs/`, `AGENTS.md`, `CLAUDE.md`, `skills/`, or `scripts/` without explicit human override.
4. **Evidence-first** — every content edit must be grounded in the knowledge model (`knowledge/{family}/{platform}/`). Read `model.yaml` before touching any content page.
5. **Knowledge freshness** — if `model.yaml` has `stale_since != null`, stop and run the maintenance workflow (S-12 → S-14) before editing content.

## Do / Don't

- **Do** check `knowledge/` artifacts before writing any content
- **Do** include evidence citations in content pages
- **Do** run ground-check (S-23) before committing content changes
- **Don't** fabricate API names, format claims, or code snippets — all must come from knowledge files
- **Don't** skip the skill chain defined in AGENTS.md Section 6
- **Don't** commit content without the evidence proof required by AGENTS.md Section 10
