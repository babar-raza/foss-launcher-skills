# CODEX.md — Codex Agent Instructions

> This file is the Codex-specific counterpart to `CLAUDE.md`. Read `AGENTS.md` for the
> full authoritative governance — this file covers Codex-specific setup only.

## Read Order

1. `AGENTS.md` — governance rules, skill chains, evidence requirements
2. This file (`CODEX.md`)
3. `knowledge/{family}/{platform}/model.yaml` — for the target product
4. `knowledge/{family}/{platform}/claims.md` — verify claims are current
5. `knowledge/{family}/{platform}/api_surface.md` — for API grounding

## Setup

Configure the content repo path before running content-writing skills:
```bash
export CONTENT_REPO_PATH=/path/to/your/content-repo
```

## Skills

Skills are in `.agents/skills/`. Each skill has its own directory with a `SKILL.md` file.
Cross-skill references like `/evidence-cite` refer to sibling skills in that directory.

## Critical Rules

1. **Evidence-first** — every content edit must be grounded in the knowledge model (`knowledge/{family}/{platform}/`). Read `model.yaml` before touching any content page.
2. **Knowledge freshness** — if `model.yaml` has `stale_since != null`, stop and run the maintenance workflow (S-12 → S-14) before editing content.
3. **Configure content root** — set `$CONTENT_REPO_PATH` before any content operation that reads or writes content files.
4. **Forbidden write paths** — never write to `themes/`, `layouts/`, `configs/`, `AGENTS.md`, `CODEX.md`, `CLAUDE.md`, `.claude/`, `.agents/`, `.kilocode/`, `skills/`, or `scripts/` without explicit human override.

## Do / Don't

- **Do** check `knowledge/` artifacts before writing any content
- **Do** include evidence citations in content pages
- **Do** run ground-check (S-23) before committing content changes
- **Don't** fabricate API names, format claims, or code snippets — all must come from knowledge files
- **Don't** skip the skill chain defined in AGENTS.md Section 6
- **Don't** commit content without the evidence proof required by AGENTS.md Section 10
