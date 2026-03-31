# CODEX.md — Codex Agent Instructions

> This file is the Codex-specific counterpart to `CLAUDE.md`. Read `AGENTS.md` for the
> full authoritative governance — this file covers Codex-specific setup only.

## Read Order

1. `AGENTS.md` — governance rules, skill chains, evidence requirements
2. This file (`CODEX.md`)
3. `knowledge/{family}/{platform}/model.yaml` — for the target product
4. `knowledge/{family}/{platform}/claims.md` — verify claims are current
5. `knowledge/{family}/{platform}/api_surface.md` — for API grounding

## Skills

Skills are in `.agents/skills/`. Each skill has its own directory with a `SKILL.md` file.
Cross-skill references like `/evidence-cite` refer to sibling skills in that directory.

## Critical Rules

1. **Evidence-first** — every content edit must be grounded in the knowledge model (`knowledge/{family}/{platform}/`). Read `model.yaml` before touching any content page.
2. **Knowledge freshness** — if `model.yaml` has `stale_since != null`, stop and run the maintenance workflow (S-12 → S-14) before editing content.
3. **Forbidden write paths** — never write to `themes/`, `layouts/`, `configs/`, `AGENTS.md`, `CODEX.md`, `CLAUDE.md`, `.claude/`, `.agents/`, `.kilocode/`, or `skills/` without explicit human override.
4. **Skill-first execution** — every task must be attempted through registered skills first (AGENTS.md §6a). If no skill covers the requirement, classify capability as FULL/PARTIAL/NONE/BROKEN per §6b and produce a gap escalation report. Do not invent ad hoc workflows.

## Do / Don't

- **Do** check `knowledge/` artifacts before writing any content
- **Do** include evidence citations in content pages
- **Do** run ground-check (S-23) before committing content changes
- **Do** classify capability (FULL/PARTIAL/NONE/BROKEN) per AGENTS.md §6b before starting novel or multi-part requests
- **Don't** fabricate API names, format claims, or code snippets — all must come from knowledge files
- **Don't** skip the skill chain defined in AGENTS.md Section 6
- **Don't** commit content without the evidence proof required by AGENTS.md Section 10
- **Don't** bypass registered skills by performing equivalent work manually — even if the output appears correct (AGENTS.md §11)

## Alignment

This file must stay aligned with AGENTS.md. When AGENTS.md §6, §6a, §6b, §7, §8, or §11
are updated, update the corresponding rules here. The canonical source is always AGENTS.md.
