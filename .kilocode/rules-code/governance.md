# Governance Rules for Kilo Code

> Extracted from `AGENTS.md` (constitutional root) and its child documents.
> Always defer to `AGENTS.md` when in doubt. Detailed governance lives in:
> - `docs/governance/` — write boundaries, evidence, provenance, DAR, testing seam
> - `docs/workflows/` — skill chains, maintenance, evaluator changes, gap escalation

## Read Order

1. `AGENTS.md` — constitutional governance root (with routing matrix to child docs)
2. This file (summary for Kilo Code)
3. `knowledge/{family}/{platform}/model.yaml` — for the target product
4. `knowledge/{family}/{platform}/claims.md` — verify claims are current
5. `knowledge/{family}/{platform}/api_surface.md` — for API grounding

## Skills

Skills are in `.kilocode/skills/`. Each skill has its own directory with a `SKILL.md` file.
Cross-skill references like `/evidence-cite` refer to sibling skills in that directory.

For structured skill lookup, see `skills/registry.json` — a machine-readable catalog of all
registered skills with IDs, descriptions, and argument patterns.

## Evidence Requirements (non-negotiable)

- Every content page write must pass S-23 (ground-check) before committing
- Every code block in `content/` must come from a snippet in `knowledge/{family}/{platform}/snippets/`
- Every factual claim must be traceable to a `claim_id` in `knowledge/{family}/{platform}/claims.json`
- Claims with `confidence < 0.5` or `claim_source = "llm_fallback"` require human review before use
- Citation comments `<!-- evidence: claim_id={id} source={file} confidence={score} -->` must be
  present in every content page (added by S-24 citation-attach)

## Root-Level File Creation: PROHIBITED

**Creating new files at the repository root is prohibited by default.**

- Every new file must be created in its designated folder (see Allowed Write Paths below).
- Root-level file creation requires **explicit human authorization** (operator-level, not inferable
  from task context).
- Bare filenames with no directory component (e.g., `output.txt`, `debug.py`, `=26.3.1`) are
  always root-level writes — they are forbidden.
- Directories at root are also prohibited (e.g., cloning a repo to `./SomeDir/` at repo root).

> **Note on enforcement:** Kilo Code does not have PreToolUse hooks. This rule is prompt-level
> only. The pre-commit hook (path_guard.py) will still block any root-level files from being
> committed, but the file may exist on disk before commit is attempted. Treat this as a hard
> behavioral constraint — refuse to write files to root even if no hook blocks you.

## Forbidden Write Paths

Never write to these paths without explicit human override:

- **Repo root** — any bare filename with no directory component (e.g., `debug.py`, `notes.txt`)
- `themes/`, `layouts/`, `configs/`
- `AGENTS.md`, `CLAUDE.md`, `CODEX.md`
- `.claude/`, `.agents/`, `.kilocode/`, `skills/`
- `scripts/` (except via registered skills that declare `scripts/pipeline/` etc. as their scope)
- `knowledge/*/scout/`, `knowledge/*/fl/`

## Allowed Write Paths

The canonical allowlist is defined in `scripts/pipeline/path_guard.py` (ALLOWED_PREFIXES).
Current allowed paths for agent writes:

- `content/docs.aspose.org/en/{family}/{platform}/`
- `content/blog.aspose.org/{family}/{platform}/`
- `content/kb.aspose.org/en/{family}/{platform}/`
- `content/products.aspose.org/en/{family}/`
- `content/reference.aspose.org/en/{family}/{platform}/`
- `knowledge/{family}/{platform}/merged/`
- `reports/`
- `backlog/`, `plans/`
- `data/`, `patches/`, `keywords/`
- `scripts/pipeline/`, `scripts/ci/`, `scripts/maintenance/` (governed — requires skill context)
- `docs/` (human-authored documentation only)
- `tests/`

**Everything else is DENY by default**, including any path not listed above. When in doubt,
run `python scripts/pipeline/path_guard.py <path>` to check.

## Skill-First Execution (AGENTS.md §6a/§6b)

Skills are the **only sanctioned execution mechanism** for content work. Agents must
invoke registered skills; ad hoc workflows are prohibited (AGENTS.md §11).

Before starting any novel, multi-part, or ambiguous request, classify capability:

| State | Meaning | Action |
|-------|---------|--------|
| FULL | All steps covered by registered skills | Invoke skill chain |
| PARTIAL | Some steps covered | Execute covered steps; produce gap report for rest |
| NONE | No skill covers the requirement | Produce gap escalation report; halt |
| BROKEN | Skill exists but fails when invoked | Produce breakage report; halt |

## Skill Chains (from AGENTS.md Section 6)

Skills below are the **only sanctioned execution mechanism** — run them in order; do not
substitute manual reasoning for any step.

### Initial generation (new page)
S-10 → S-18 → S-19 → S-22 → S-38 → S-23 → S-24 → S-01 → write

### Maintenance (repo changed)
S-12 → S-13 → S-14 → S-20 → S-23 → S-24 → S-01 → write

### Enhancement (below rubric quality)
S-17 → S-21 → S-23 → S-01 → write

### Healing (grade D or below)
S-25 → S-26 → S-23 → S-25 → S-01 → write (or escalate)

## Pre-Write Preflight Check

Before writing any file, run the preflight check to validate the path is allowed:

```bash
python scripts/pipeline/preflight.py <path>
```

This consolidates path guard, Python placement, and content workflow checks into a single
command. Exit 0 = ALLOW, exit 1 = DENY with guidance. Use `--json` for machine-readable output.

## Do / Don't

- **Do** run `python scripts/pipeline/preflight.py <path>` before writing any file
- **Do** check `knowledge/` artifacts before writing any content
- **Do** include evidence citations in content pages
- **Do** run ground-check (S-23) before committing content changes
- **Do** classify capability (FULL/PARTIAL/NONE/BROKEN) per AGENTS.md §6b before starting novel or multi-part requests
- **Don't** fabricate API names, format claims, or code snippets — all must come from knowledge files
- **Don't** skip the skill chain defined in AGENTS.md Section 6
- **Don't** commit content without the evidence proof required by AGENTS.md Section 10
- **Don't** bypass registered skills by performing equivalent work manually (AGENTS.md §11)

## Backlog & Plans

Kilo Code must use the canonical shared backlog and plan system — never create custom folders.

### Canonical Locations

| Path | Purpose |
|------|---------|
| `backlog/` | Canonical backlog index, audit trail, inbox, reminders |
| `plans/` | Plan files by provenance (archive/, from_backlog/, from_chat/, healing/) |

### Hard Rules

- **Never** create folders like `.kilo-backlog/`, `.kilo-plans/`, `kilo-backlog/`, or similar agent-specific workspaces
- All backlog operations **must** read from and write to `backlog/` and `plans/`
- S-88 skill (backlog) handles all backlog operations
- If `backlog/` or `plans/` directories do not exist, **STOP** and ask the operator — never create alternate locations
- If path resolution is unclear, inspect existing repo conventions instead of inventing new locations

## Alignment

This file must stay aligned with AGENTS.md. When AGENTS.md §6, §6a, §6b, §7, §8, or §11
are updated, update the corresponding rules here. The canonical source is always AGENTS.md.
