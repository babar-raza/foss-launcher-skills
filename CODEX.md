# CODEX.md — Codex Agent Instructions

> This file is the Codex-specific counterpart to `CLAUDE.md`. Read `AGENTS.md` for the
> full authoritative governance — this file covers Codex-specific setup only.

## Read Order

1. `AGENTS.md` — constitutional governance root. Its own Section Index (top of the file)
   is the authoritative map of which topic lives in which child document under
   `docs/governance/`, `docs/workflows/`, and `docs/reference/` — follow that table rather
   than a paraphrase here, since child-doc locations move independently of this file and a
   second description of them just drifts (found live 2026-08-07: this line previously
   claimed `docs/governance/` covered "write boundaries, evidence, provenance, DAR, testing
   seam," but that directory now holds only `dar-table.md`, `planning-methodology.md`, and
   `backlink-policy.md` — the rest moved inline into AGENTS.md itself or into
   `docs/_archive/pre-refactor/governance/` during an earlier refactor).
2. This file (`CODEX.md`)
3. `knowledge/{family}/{platform}/model.yaml` — for the target product
4. `knowledge/{family}/{platform}/claims.md` — verify claims are current
5. `knowledge/{family}/{platform}/api_surface.md` — for API grounding

## Skills

Skills are in `.agents/skills/`. Each skill has its own directory with a `SKILL.md` file.
Cross-skill references like `/evidence-cite` refer to sibling skills in that directory.

For structured skill lookup, see `skills/registry.json` — a machine-readable catalog of all
registered skills with IDs, descriptions, and argument patterns.

## Critical Rules

1. **Evidence-first** — every content edit must be grounded in the knowledge model (`knowledge/{family}/{platform}/`). Read `model.yaml` before touching any content page.
2. **Knowledge freshness** — if `model.yaml` has `stale_since != null`, stop and run the maintenance workflow (S-12 → S-14) before editing content.
3. **Forbidden write paths** — never write to `themes/`, `layouts/`, `configs/`, `AGENTS.md`, `CODEX.md`, `CLAUDE.md`, `.claude/`, `.agents/`, `.kilocode/`, or `skills/` without explicit human override.
4. **Skill-first execution** — every task must be attempted through registered skills first (AGENTS.md §6a). If no skill covers the requirement, classify capability as FULL/PARTIAL/NONE/BROKEN per §6b and produce a gap escalation report. Do not invent ad hoc workflows.
5. **Planning discipline** — before treating any newly-authored multi-step plan as ready to execute, self-check it against AGENTS.md §17 (`docs/governance/planning-methodology.md`): apply the Planning Review Checklist and Taskcard Readiness Checklist, and bind multi-session missions to the existing `MISSION_AUTHORITY.yaml` / schema-5f taskcard mechanisms rather than inventing a new tracker. Most of this remains a self-administered check (there is no CI gate for it), but the one mechanically-checkable rule — don't invent a parallel mission/taskcard tracker — has a real, runnable command. Run it against the plan you draft, before presenting it as final:
   ```bash
   .venv/Scripts/python scripts/ci/checks/check_plan_origination.py <drafted-plan-file>
   ```
   Exit 0 means the plan is clean or correctly cites the existing mechanism; exit 1 prints the specific violation (e.g. an inline `mission_id:`/`taskcards:` block with no citation of `MISSION_AUTHORITY.yaml` / `reports/plan_state/` / `taskcards.jsonl` / `backlog/BACKLOG.md`) — fix the plan to bind to the real mechanism rather than the invented one.

## Pre-Write Preflight Check

Before writing any file, run the preflight check to validate the path is allowed:

```bash
.venv/Scripts/python scripts/pipeline/commands/launch/preflight.py <path>
```

This consolidates path guard, Python placement, and content workflow checks into a single
command. Exit 0 = ALLOW, exit 1 = DENY with guidance. Use `--json` for machine-readable output.

## Do / Don't

- **Do** run `.venv/Scripts/python scripts/pipeline/commands/launch/preflight.py <path>` before writing any file
- **Do** check `knowledge/` artifacts before writing any content
- **Do** include evidence citations in content pages
- **Do** run ground-check (S-23) before committing content changes
- **Do** classify capability (FULL/PARTIAL/NONE/BROKEN) per AGENTS.md §6b before starting novel or multi-part requests
- **Don't** fabricate API names, format claims, or code snippets — all must come from knowledge files
- **Don't** skip the skill chain defined in AGENTS.md Section 6
- **Don't** commit content without the evidence proof required by AGENTS.md Section 10
- **Don't** bypass registered skills by performing equivalent work manually — even if the output appears correct (AGENTS.md §11)

## Alignment

This file must stay aligned with AGENTS.md. When AGENTS.md §6, §6a, §6b, §7, §8, §11, or §17
are updated, update the corresponding rules here. The canonical source is always AGENTS.md.
