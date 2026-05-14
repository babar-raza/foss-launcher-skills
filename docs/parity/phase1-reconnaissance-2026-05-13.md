# Phase 1 Reconnaissance - Skill Parity Program

Date: 2026-05-13

## Phase Goal

Map both repositories at high level and identify every likely skill-system surface before building normalized inventories.

## Inputs

- Source set A: `D:/onedrive/Documents/GitHub/aspose.org`
- Source set B: `C:/Users/prora/OneDrive/Documents/GitHub/foss-launcher-skills-gitlab`
- Governing instruction: treat `aspose.org` as reference/read-only and do not write to `aspose.org/content`.

## Outputs

- High-level repo map for both repositories.
- Candidate source-of-truth surfaces for skill registration, execution, policy, and testing.
- Normalized inventory schema to use in Phases 2 and 3.
- Evidence-based comparison method for distinguishing same filenames from same practical features.
- Initial assumptions log and unresolved ambiguities.

## Exit Criteria

- A defensible repo map exists for both repos.
- All likely skill system surfaces are identified for deeper inventory.
- The inventory schema is explicit enough to support feature-level, behavior-level, dependency-level, and governance-level comparison.

## Repository Map - aspose.org

Role: Hugo website repo and embedded reference implementation for the skills system.

Observed root surfaces:

- Governance and agent instructions: `AGENTS.md`, `CODEX.md`, `CLAUDE.md`, `.kilocode/rules-code/`, `docs/governance/`, `docs/workflows/`, `docs/registries/`.
- Canonical or provider skill trees:
  - `skills/` contains markdown skill catalog and `skills/registry.json`.
  - `.agents/skills/` contains Codex-style directories with `SKILL.md`.
  - `.claude/commands/` contains slash-command markdown files.
  - `.kilocode/skills/` contains Kilo Code skill directories.
- Backing implementation:
  - `scripts/pipeline/commands/` by domain: `content`, `diagnostics`, `enrichment`, `governance`, `healing`, `knowledge`, `launch`, `ops`.
  - `scripts/pipeline/content_eval/`, `scripts/gap-eval/`, `scripts/translator/`, `scripts/pipeline/lib/`, `scripts/pipeline/core/`.
  - `scripts/ci/checks/`, `scripts/ci/hooks/`, `scripts/ci/tests/`.
- CI and governance workflows: `.github/workflows/ci-eval-consistency.yml`, `content-audit.yml`, `extraction-pipeline.yml`, `skill-governance.yml`.
- Runtime/source dependencies: `knowledge/`, `runs/.clone_cache/`, `content/`, `themes/`, `layouts/`, `configs/`, `data/`, `reports/`, `backlog/`, `plans/`.

Evidence gathered:

- `.agents/skills` has 81 `SKILL.md` files.
- `.kilocode/skills` has 81 `SKILL.md` files.
- `.claude/commands` has 75 files at max depth 1.
- `scripts/pipeline` plus `scripts/ci` contains a large backing surface: 1403 files at max depth 4 in the initial count, including pycache.
- `skills/registry.json` reports `schema_version: 1`, `generated_from: "skills/*.md"`, `generated_by: "scripts/pipeline/commands/ops/sync_providers.py"`, and `skill_count: 81`.
- `docs/registries/skills.md` lists detailed S-IDs, skill purposes, implementation notes, and enforcement scripts.

Initial aspose.org source-of-truth candidates:

- Formal registry: `skills/registry.json`.
- Canonical markdown catalog: `skills/*.md` plus `skills/README.md`.
- Provider mirrors: `.agents/skills/*/SKILL.md`, `.claude/commands/*.md`, `.kilocode/skills/*/SKILL.md`.
- Registry/generation tooling: `scripts/pipeline/commands/ops/sync_providers.py`, `scripts/pipeline/commands/ops/sync_skills.py`, `scripts/ci/checks/check_skill_registry.py`, `scripts/ci/checks/check_skill_registry_json.py`, `scripts/ci/checks/check_skill_readme_coverage.py`, `scripts/ci/checks/check_script_skill_sync.py`, `scripts/ci/checks/validate_skill_ids.py`.
- Execution backing: skill-referenced scripts under `scripts/pipeline/commands/`, `scripts/pipeline/content_eval/`, `scripts/gap-eval/`, `scripts/translator/`.
- Governance backing: `AGENTS.md`, `CODEX.md`, `CLAUDE.md`, docs under `docs/governance/`, `docs/workflows/`, `docs/registries/`, CI hooks/checks.

## Repository Map - foss-launcher-skills-gitlab

Role: standalone skills repository intended to provide cleaner, better organized, better documented, better governed, and better maintained representation of the skills system.

Observed root surfaces:

- Governance and agent instructions: `AGENTS.md`, `AGENTS.template.md`, `CODEX.md`, `CLAUDE.md`, `CONVENTIONS.md`, `OPERATOR_GUIDE.md`, `QUICKSTART.md`, `README.md`.
- Canonical or provider skill trees:
  - `skills/` contains markdown skill catalog and `skills/registry.yaml`.
  - `.agents/skills/` contains Codex-style directories with `SKILL.md`.
  - `.claude/commands/` contains slash-command markdown files.
  - `.kilocode/skills/` contains Kilo Code skill directories.
- Backing implementation:
  - Standalone scripts: `scripts/scout.py`, `scripts/merge.py`, `scripts/materialize.py`, `scripts/verify.py`, `scripts/corpus_scan.py`, `scripts/discover.py`, `scripts/path_guard.py`, and related utilities.
  - Migrated pipeline scripts: `scripts/pipeline/commands/`, `scripts/pipeline/content_eval/`, `scripts/pipeline/lib/`, `scripts/translator/`.
  - Tests and fixtures: `tests/`, `tests/fixtures/`.
- CI and governance workflows: `.github/workflows/eval-consistency.yml`, `pipeline-tests.yml`, `skill-governance.yml`, `skill-registry-audit.yml`, plus `.gitlab-ci.yml`.
- Runtime/source dependencies: `config.yaml`, `configs/`, `knowledge/`, `golden/`, `repos/`, `runs/`, `output/`, `intake/`, `reports/`, `tools/`.

Evidence gathered:

- `.agents/skills` has 89 `SKILL.md` files.
- `.kilocode/skills` has 89 `SKILL.md` files.
- `.claude/commands` has 82 files at max depth 1.
- `skills/registry.yaml` is explicitly documented as a "Single authoritative source of truth for all skill IDs, names, and script bindings."
- `skills/registry.yaml` claims validation by `python scripts/validate_skills.py` and includes rules for ID uniqueness, `skills/{name}.md` coverage, `.claude/commands/{name}.md` byte identity after frontmatter stripping, script path existence, and internal-skill exclusion from `.claude/commands/`.
- `README.md` presents the standalone repo as a library of 89 skills and documents standalone operation against an external content repo.
- `README.md` shows standalone-specific capabilities not obviously present as aspose.org registered skills: `truth-sync`, `corpus-scan`, `discover-products`, `evidence-decide`, `evidence-materialize`, `mental-model`, `evidence-verify`, and `ground-check`.
- `tests/` includes unit and fixture tests for standalone utilities such as setup, config loader, corpus scan, discover, scout, merge, materialize, mental model, verify, sync, hooks, and validation.

Initial standalone source-of-truth candidates:

- Formal registry: `skills/registry.yaml`.
- Canonical markdown catalog: `skills/*.md`.
- Provider mirrors: `.agents/skills/*/SKILL.md`, `.claude/commands/*.md`, `.kilocode/skills/*/SKILL.md`.
- Registry/generation tooling: `scripts/validate_skills.py`, `scripts/sync_agents.py`, `scripts/sync_commands.py`, `scripts/readme_sync.py`, `scripts/_skill_constants.py`.
- Execution backing: script paths declared in `skills/registry.yaml`, standalone scripts under `scripts/`, and migrated pipeline scripts under `scripts/pipeline/`.
- Governance backing: `AGENTS.md`, `CONVENTIONS.md`, `README.md`, `QUICKSTART.md`, `OPERATOR_GUIDE.md`, `.github/workflows/*`, `.gitlab-ci.yml`, tests.

## Initial Cross-Repo Observations

- The repos do not use the same registry format: aspose.org uses `skills/registry.json`; the standalone repo uses `skills/registry.yaml` with script bindings.
- Skill names alone are insufficient:
  - Several names exist in both repos but can bind to different script paths, IDs, or expected repo layouts.
  - The standalone repo has additional skill names that may represent genuine improvements or may be wrappers around capabilities already hidden inside aspose.org.
  - aspose.org has site-specific governance hooks, content path rules, clone-cache rules, Hugo/theme/content coupling, and CI surfaces that may be required for practical behavior but are not represented by skill prompt files alone.
- Provider mirrors are part of practical behavior:
  - aspose.org has 81 Codex/Kilo skills and 75 Claude command files.
  - standalone has 89 Codex/Kilo skills and 82 Claude command files.
  - The count differences may be intentional internal-skill hiding, missing registrations, or extra standalone capabilities. This is unproven until Phases 2-4.
- Existing standalone docs in `docs/parity/` are already modified in the worktree; this Phase 1 artifact was added as a new file to avoid overwriting existing work.

## Inventory Schema for Phases 2 and 3

Each normalized inventory record will use this schema:

```yaml
canonical_name:
repo:
repo_path:
provider_paths:
  canonical_markdown:
  codex_skill:
  claude_command:
  kilocode_skill:
id:
role_purpose:
feature_group:
trigger_invocation:
inputs:
outputs:
side_effects:
write_paths:
forbidden_paths:
dependencies:
  skills:
  scripts:
  modules:
  configs:
  docs_contracts:
  tests:
  fixtures:
  external_tools:
  repo_layout:
config_keys:
required_environment:
governance_hooks:
ci_references:
entrypoints:
generated_artifacts:
runtime_state:
source_of_truth_files:
maturity_status:
feature_status:
verification_status:
evidence:
  files:
  commands:
  snippets:
confidence:
ambiguities:
notes:
```

Repository-level inventory records will also capture:

```yaml
repo:
role:
skill_tree_counts:
registries:
provider_mirrors:
operator_docs:
governance_docs:
script_roots:
test_roots:
fixture_roots:
ci_workflows:
hooks:
runtime_data_roots:
content_or_external_repo_coupling:
known_forbidden_write_paths:
known_output_roots:
known_discovery_mechanisms:
known_sync_mechanisms:
known_validation_mechanisms:
```

## Evidence-Based Equivalence Method

Two skills or capabilities will be considered equivalent only when the standalone repo can produce the same practical user outcome with equivalent or better execution coverage, reliability, discoverability, governance, documentation, configurability, testability, and maintainability.

Comparison will use these checks, in this order:

1. Name and registry identity: compare slug, ID, category, internal/user-callable status, registry entry, and provider mirror presence.
2. Contract equivalence: compare arguments, prerequisites, hard stops, write paths, output artifacts, dry-run behavior, and declared skill chains.
3. Backing implementation: compare referenced scripts/modules, CLI flags, config keys, environment variables, helper utilities, and expected repo layout.
4. Governance equivalence: compare path guards, evidence gates, no-downgrade rules, hooks, CI checks, protected paths, registration checks, and commit/readiness rules.
5. Test and fixture equivalence: compare unit tests, smoke tests, fixtures, dry-run tests, provider sync tests, and negative/safety tests.
6. Execution proof: run non-destructive checks where feasible using temporary worktrees, fixtures, redirected output roots, dry-run modes, or synthetic content.
7. Maintainability check: identify where standalone implements the same outcome with cleaner organization, better script binding, better docs, or stronger tests.

Status values for Phase 4:

- exact parity proven
- functional parity proven through different implementation
- partial parity
- governance-only present
- documented but not implemented
- implemented but not registered/discoverable
- implemented but not verified
- missing entirely
- unclear, requires investigation

Gap classifications for Phase 4:

- missing skill
- missing part of a skill
- missing dependency
- missing registration
- missing governance
- missing documentation
- missing examples
- missing test coverage
- missing config support
- missing helper utility
- organizational weakness
- naming/structure mismatch
- hidden feature not surfaced cleanly
- behavioral mismatch
- verification gap

## Assumptions Log

- A1: aspose.org remains the reference implementation for practical behavior during this sprint. Status: given by operator and supported by root governance.
- A2: standalone repo is the destination for all new planning, taskcards, migration, and verification artifacts unless a stronger placement is justified. Status: given by operator.
- A3: existing dirty worktree changes in standalone are user-owned and must not be overwritten. Status: observed via `git status --short`.
- A4: `skills/registry.yaml` in standalone is intended to be authoritative for standalone skill IDs and script bindings. Status: evidenced by registry comments; behavior still requires validation.
- A5: `skills/registry.json` in aspose.org is a generated catalog and not sufficient alone to prove behavior. Status: evidenced by `generated_from` and separate backing scripts/governance docs.

## Unresolved Ambiguities

- Whether all standalone extra skills are true feature improvements, renames, wrappers around aspose.org hidden features, or unverified stubs.
- Whether every aspose.org skill has a working standalone equivalent despite ID/name differences.
- Whether standalone script bindings in `skills/registry.yaml` all point to current runnable scripts.
- Whether provider mirrors are byte-equivalent or intentionally divergent in either repo.
- Whether aspose.org governance hooks have standalone equivalents or should remain site-repo-only constraints.
- Whether existing `docs/parity/*` worktree modifications already contain useful prior parity findings; they must be read in later phases without overwriting.

## Phase 1 Decisions

- Treat `aspose.org` as read-only reference during this sprint.
- Do not touch `aspose.org/content`.
- Use a behavior-first inventory schema, not a file-name inventory.
- Record evidence at file/command level for every inventory claim in Phases 2 and 3.
- Add this new Phase 1 report rather than modifying existing standalone parity documents because the standalone worktree is already heavily dirty.

## Taskcards Created Or Updated

No implementation taskcards were created in Phase 1. Taskcard creation belongs to Phase 6 after inventories, parity analysis, and target-state design.

Phase 2 will create analysis work items only if a blocker prevents completing the aspose.org inventory in one pass.

## Next Phase Entry Criteria

Phase 2 can begin when:

- This reconnaissance note exists in the standalone repo.
- The inventory schema above is accepted as the working schema.
- aspose.org remains available for read-only inspection.
- No process requires writing to `aspose.org/content`.

