# aspose.org Skill Inventory

Date: 2026-05-13

## Phase Goal

Extract the full normalized skill-system inventory for the source repository.

## Exit Criteria Status

Met for inventory extraction: normalized records were created for every discovered skill slug. Behavioral parity is not concluded in this phase.

## Counts

- `skills_markdown`: 82
- `codex_agents_skills`: 81
- `claude_commands`: 74
- `kilocode_skills`: 81
- `registry_skill_count`: 81
- `normalized_records`: 84

## Provider Gaps

- `canonical_markdown` missing for 2 records: seo-review, translate
- `codex_skill` missing for 3 records: content-enrich, seo-review, translate
- `claude_command` missing for 10 records: change-guard, evidence-cite, gap-plan, knowledge-bootstrap, no-downgrade-guard, path-guard, project-phase-store, rubric-align, translate-batch, translate-page
- `kilocode_skill` missing for 3 records: content-enrich, seo-review, translate

## Registry And Entrypoint Signals

- Unregistered/provider-only records: 3 - content-enrich, seo-review, translate
- Records with no backing script detected in skill text: 3

## High-Confidence Surfaces

### registries

- `skills/registry.json`
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
- `scripts/pipeline/tests/`
- `scripts/ci/tests/`

### ci_workflows

- `.github/workflows/ci-eval-consistency.yml`
- `.github/workflows/content-audit.yml`
- `.github/workflows/extraction-pipeline.yml`
- `.github/workflows/skill-governance.yml`

### hooks

- `scripts/ci/hooks/_gov_block.sh`
- `scripts/ci/hooks/bootstrap_session_gate.sh`
- `scripts/ci/hooks/capture_proof_bundle.sh`
- `scripts/ci/hooks/check_content_edit_hook.sh`
- `scripts/ci/hooks/check_content_write_hook.sh`
- `scripts/ci/hooks/check_destructive_bash_hook.sh`
- `scripts/ci/hooks/check_hugo_build.sh`
- `scripts/ci/hooks/check_py_write_hook.sh`
- `scripts/ci/hooks/check_session_gate.sh`
- `scripts/ci/hooks/check_shell_bash.sh`
- `scripts/ci/hooks/check_skill_context_hook.sh`
- `scripts/ci/hooks/check_venv.sh`
- `scripts/ci/hooks/check_venv_bash_hook.sh`
- `scripts/ci/hooks/check_write_path_hook.sh`
- `scripts/ci/hooks/find_python.sh`
- `scripts/ci/hooks/repair_venv.sh`
- `scripts/ci/hooks/run_proof_harness.sh`
- `scripts/ci/hooks/simulate_pr_checks.sh`
- `scripts/ci/hooks/smoke_chain.sh`

## Unresolved Ambiguities

- Prompt-only records require behavioral review before parity conclusions.
- Detected script paths prove references, not execution success.
- Provider mirror divergence requires dedicated sync/byte comparison checks.
