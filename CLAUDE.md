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

## Read Order

Always read in this order before doing any work:

1. `AGENTS.md` — governance rules, skill chains, evidence requirements
2. This file (`CLAUDE.md`)
3. `knowledge/{family}/{platform}/model.yaml` — for the target product
4. `knowledge/{family}/{platform}/claims.md` — verify claims are current
5. `knowledge/{family}/{platform}/merged/api_surface.md` — for API grounding

## Critical Rules

1. **Read AGENTS.md first** — it is the authoritative governance file for all content work.
2. **Forbidden write paths** — never write to `themes/`, `layouts/`, `configs/`, `AGENTS.md`, `CODEX.md`, `CLAUDE.md`, `.claude/`, `.agents/`, `.kilocode/`, `skills/`, or `scripts/pipeline/path_guard.py` without explicit human override.
3. **Evidence-first** — every content edit must be grounded in the knowledge model (`knowledge/{family}/{platform}/`). Read `model.yaml` before touching any content page.
4. **Knowledge freshness** — if `model.yaml` has `stale_since != null`, stop and run the maintenance workflow (S-12 → S-14) before editing content.
5. **Activate .venv** — always use `.venv/Scripts/python` (Windows) or `.venv/bin/python` (Unix) rather than system Python for all scripts.
6. **Skill-first execution** — every task must be attempted through registered skills first (AGENTS.md §6a). If no skill covers the requirement, classify capability as FULL/PARTIAL/NONE/BROKEN per §6b and produce a gap escalation report. Do not invent ad hoc workflows.

## Skills

Skills are in `skills/` (canonical source). The Claude Code subset is in `.claude/commands/`
(43 user-callable skills). Invoke skills using the `Skill` tool with the skill name and
arguments.

**Internal skills** (knowledge-bootstrap S-54, path-guard S-01, evidence-cite S-24,
change-guard S-33, no-downgrade-guard S-55, rubric-align S-17, gap-plan S-44,
project-phase-store S-10) are not user-callable via the Skill tool. Orchestrator skills
(e.g., `launch-product`, `new-docs-page`) handle these internally as part of their own
procedure. Do not attempt to call internal skills directly — follow the orchestrator skill
chain from §6 of AGENTS.md instead.

Cross-skill references in skill files (e.g., `/knowledge-bootstrap`) denote steps the
orchestrator handles internally. They are not slash commands to be issued separately.

## Pre-Task Protocol

Before starting any content or knowledge task:

1. Read `AGENTS.md` (or confirm it is already in session context)
2. Read `knowledge/{family}/{platform}/model.yaml` for the target product
3. If `stale_since` is not null → stop; run S-12 → S-14 before continuing
4. State a capability assessment (AGENTS.md §6b): FULL / PARTIAL / NONE / BROKEN
5. For FULL: invoke the matching skill chain from AGENTS.md §6
6. For PARTIAL/NONE: produce gap escalation report to `reports/skill-gaps/`; do not proceed ad hoc

## Do / Don't

- **Do** check `knowledge/` artifacts before writing any content
- **Do** include evidence citations in content pages
- **Do** run ground-check (S-23) before committing content changes
- **Do** classify capability (FULL/PARTIAL/NONE/BROKEN) per AGENTS.md §6b before starting novel or multi-part requests
- **Do** activate `.venv` before running any Python scripts
- **Don't** fabricate API names, format claims, or code snippets — all must come from knowledge files
- **Don't** skip the skill chain defined in AGENTS.md Section 6
- **Don't** commit content without the evidence proof required by AGENTS.md Section 10
- **Don't** bypass registered skills by performing equivalent work manually — even if the output appears correct (AGENTS.md §11)
- **Don't** use system Python — always use `.venv/Scripts/python` or `.venv/bin/python`

## Alignment

This file must stay aligned with AGENTS.md. When AGENTS.md §6, §6a, §6b, §7, §8, or §11
are updated, update the corresponding rules here. The canonical source is always AGENTS.md.
