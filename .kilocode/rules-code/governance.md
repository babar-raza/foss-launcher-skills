# Governance Rules for Kilo Code

> Extracted from `AGENTS.md` — the full authoritative governance file.
> Always defer to `AGENTS.md` when in doubt.

## Read Order

1. `AGENTS.md` — full governance rules
2. This file (summary for Kilo Code)
3. `knowledge/{family}/{platform}/model.yaml` — for the target product
4. `knowledge/{family}/{platform}/claims.md` — verify claims are current
5. `knowledge/{family}/{platform}/api_surface.md` — for API grounding

## Skills

Skills are in `.kilocode/skills/`. Each skill has its own directory with a `SKILL.md` file.
Cross-skill references like `/evidence-cite` refer to sibling skills in that directory.

## Evidence Requirements (non-negotiable)

- Every content page write must pass S-23 (ground-check) before committing
- Every code block in `content/` must come from a snippet in `knowledge/{family}/{platform}/snippets/`
- Every factual claim must be traceable to a `claim_id` in `knowledge/{family}/{platform}/claims.json`
- Claims with `confidence < 0.5` or `claim_source = "llm_fallback"` require human review before use
- Citation comments `<!-- evidence: claim_id={id} source={file} confidence={score} -->` must be
  present in every content page (added by S-24 citation-attach)

## Forbidden Write Paths

Never write to these paths without explicit human override:

- `themes/`, `layouts/`, `configs/`
- `AGENTS.md`, `CLAUDE.md`, `CODEX.md`
- `.claude/`, `.agents/`, `.kilocode/`, `skills/`
- `scripts/`
- `knowledge/*/scout/`, `knowledge/*/fl/`

## Allowed Write Paths

- `content/docs.aspose.org/en/{family}/{platform}/`
- `content/blog.aspose.org/{family}/{platform}/`
- `content/kb.aspose.org/en/{family}/{platform}/`
- `content/products.aspose.org/en/{family}/`
- `content/reference.aspose.org/en/{family}/{platform}/`
- `knowledge/{family}/{platform}/merged/`
- `reports/`

## Skill Chains (from AGENTS.md Section 6)

### Initial generation (new page)
S-10 → S-18 → S-19 → S-22 → S-23 → S-24 → S-01 → write

### Maintenance (repo changed)
S-12 → S-13 → S-14 → S-20 → S-23 → S-24 → S-01 → write

### Enhancement (below rubric quality)
S-17 → S-21 → S-23 → S-01 → write

### Healing (grade D or below)
S-25 → S-26 → S-23 → S-25 → S-01 → write (or escalate)

## Do / Don't

- **Do** check `knowledge/` artifacts before writing any content
- **Do** include evidence citations in content pages
- **Do** run ground-check (S-23) before committing content changes
- **Don't** fabricate API names, format claims, or code snippets — all must come from knowledge files
- **Don't** skip the skill chain defined in AGENTS.md Section 6
- **Don't** commit content without the evidence proof required by AGENTS.md Section 10
