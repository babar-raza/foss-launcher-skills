# CONVENTIONS.md — Development Conventions

This document describes naming, structural, and workflow conventions for
the foss-launcher-skills-gitlab repository.

## File Naming

### Skills
- Canonical skill files: `skills/{slug}.md` (kebab-case slug)
- Claude Code commands: `.claude/commands/{slug}.md` (mirrored by distribute.py)
- Codex CLI skills: `.agents/skills/{slug}/SKILL.md`
- Kilo Code skills: `.kilocode/skills/{slug}/SKILL.md`

### Python Scripts
- Pipeline scripts: `scripts/pipeline/{module}.py` (snake_case)
- CI support scripts: `scripts/ci/{script}.sh` or `scripts/ci/{script}.py`
- Top-level utilities: `scripts/{tool}.py`
- Tests: `tests/test_{module}.py` for unit tests; `tests/test_e2e_{feature}.py` for E2E

### Reports and Artifacts
- Audit reports: `reports/audit/{family}-{platform}-{type}-{YYYYMMDD}.{ext}`
- Skill run records: `reports/skill-runs/{timestamp}-{slug}.json`
- Parity artifacts: `docs/parity/*.md`

## Skill IDs

- IDs are assigned sequentially: S-01, S-02, ..., S-NNN
- IDs are **never reused** — retired skills keep their ID with `retired: true` in registry
- Internal/guard skills use `internal: true` in `skills/registry.yaml`
- New skills are registered in `skills/registry.yaml` before distribution

## Commit Messages

### Format

```
{type}({scope}): {description}

Knowledge model SHA: {sha}
Ground-check result: PASS (reports/...)
Skills invoked: [S-XX, S-YY]
```

### Types
- `feat`: new skill or capability
- `fix`: bug fix or correction
- `docs`: documentation only
- `refactor`: code change without behavior change
- `test`: test additions or fixes
- `chore`: maintenance (dependency updates, config changes)

### Scopes
- `skills`: skill file changes
- `pipeline`: scripts/pipeline/ changes
- `agents`: AGENTS.md or governance changes
- `ci`: .github/workflows/ changes
- `docs`: docs/ changes
- `tests`: tests/ changes

## Python Style

- Target Python 3.10+ (match CI environment)
- Use `from __future__ import annotations` at top of all pipeline scripts
- Type hints on public functions; internal helpers may omit
- `configure()` seam pattern required for all scripts with module-level path constants
  (see AGENTS.md §16 — Testing Seam Contract)
- No bare `python` invocations in shell scripts — always use explicit path or venv

## Knowledge Model Paths

All scripts resolve paths relative to the repo root or via `$CONTENT_REPO_PATH`:

```
knowledge/{family}/{platform}/
  merged/
    model.yaml          — SHA, version, enrichment_status
    api_surface.json    — API class/method/property list
    claims.json         — enriched semantic claims
    formats.json        — supported file formats
    index.json          — coverage and surface tier
  scout/
    api_surface.json    — raw scout output
    enriched_claims.json — pre-promote enriched claims
```

Content lives in `$CONTENT_REPO_PATH/content/{site}/en/{family}/{platform}/`.

## Parity Documents

Parity artifacts live in `docs/parity/` and must be kept current:
- `inventory-aspose.md` — aspose.org skill inventory
- `inventory-foss.md` — this repo skill inventory
- `parity-matrix.md` — side-by-side comparison
- `gap-report.md` — open gaps and action items
- `verification-log.md` — non-destructive verification evidence
- `closure-report.md` — sprint closure record

## Distribution

After any skill registry change:
```
python tools/distribute.py
```
This syncs `.claude/commands/`, `.agents/skills/`, and `.kilocode/skills/` from `skills/`.

## Testing

- All pipeline scripts must have a corresponding test in `tests/`
- Use `configure()` seam for path isolation (never monkeypatch path constants)
- Fixture data goes in `tests/fixtures/`
- Set `CONTENT_REPO_PATH=tests/fixtures` in test environment

## Version Constraints

- `EVALUATOR_LOGIC_VERSION` in `content_eval/__init__.py`: bump only on break/fix
  (see AGENTS.md §9a for the full checklist)
- `skills/registry.yaml` version: set to git tag on release
