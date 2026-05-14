# foss-launcher-skills-gitlab Skill Inventory

Date: 2026-05-13

## Phase Goal

Extract the full normalized skill-system inventory for the source repository.

## Exit Criteria Status

Met for inventory extraction: normalized records were created for every discovered skill slug. Behavioral parity is not concluded in this phase.

## Counts

- `skills_markdown`: 92
- `codex_agents_skills`: 92
- `claude_commands`: 85
- `kilocode_skills`: 92
- `registry_skill_count`: 92
- `normalized_records`: 92

## Provider Gaps

- `canonical_markdown` missing for 0 records: 
- `codex_skill` missing for 0 records: 
- `claude_command` missing for 7 records: change-guard, evidence-cite, knowledge-bootstrap, no-downgrade-guard, path-guard, project-phase-store, rubric-align
- `kilocode_skill` missing for 0 records: 

## Registry And Entrypoint Signals

- Unregistered/provider-only records: 0
- Records with no backing script detected in skill text: 23

## High-Confidence Surfaces

### registries

- `skills/registry.yaml`
- `docs/registries/skills.md`
- `scripts/pipeline/config/registry.yaml`

### provider_mirrors

- `skills/*.md`
- `.agents/skills/*/SKILL.md`
- `.claude/commands/*.md`
- `.kilocode/skills/*/SKILL.md`

### script_roots

- `scripts/`
- `scripts/pipeline/commands/`
- `scripts/pipeline/content_eval/`
- `scripts/gap-eval/`
- `scripts/translator/`
- `scripts/ci/`

### test_roots

- `tests/`

### ci_workflows

- `.github/workflows/eval-consistency.yml`
- `.github/workflows/pipeline-tests.yml`
- `.github/workflows/skill-governance.yml`
- `.github/workflows/skill-registry-audit.yml`

### hooks


## Unresolved Ambiguities

- Prompt-only records require behavioral review before parity conclusions.
- Detected script paths prove references, not execution success.
- Provider mirror divergence requires dedicated sync/byte comparison checks.
