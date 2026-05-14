# Phase 1 Reconnaissance - Refreshed Skill Parity Program

Date: 2026-05-14

## Phase Goal

Map both repositories at high level, locate every likely skill-system surface, and define the shared inventory schema and behavior-first comparison method before building refreshed inventories.

## Inputs

- Source set A: `D:/onedrive/Documents/GitHub/aspose.org`
- Source set B: `C:/Users/prora/OneDrive/Documents/GitHub/foss-launcher-skills-gitlab`
- Current instruction: treat `aspose.org` as the reference implementation to inspect, do not write to `aspose.org/content`, and prefer treating all of `aspose.org` as read-only.
- Historical parity artifacts in standalone repo: `docs/parity/`, including prior inventories, taskcards, evidence, tools, and closure reports.

## Outputs

- Current high-level repo map for both repositories.
- Candidate source-of-truth surfaces for skill registration, execution, policy, governance, and testing.
- Normalized inventory schema for Phases 2 and 3.
- Evidence-based plan for distinguishing same file names from same practical features.
- Initial assumptions log and ambiguity register.

## Exit Criteria

- A defensible repo map exists for both repos.
- All likely skill-system surfaces are identified for deeper inventory.
- Historical artifacts are classified as prior evidence, not current truth.
- The inventory schema is explicit enough to support feature-level, behavior-level, dependency-level, governance-level, and verification-level comparison.

## Shell And Safety Evidence

- `C:/Program Files/Git/bin/bash.exe` is available and reports `MSYSTEM=MINGW64`, `BASH_VERSION=5.2.37(1)-release`.
- The `bash.exe` on default PATH is WSL and emitted WSL session warnings. It must not be used for governed repo operations.
- All Phase 1 repo inspection after this discovery used Git for Windows Bash explicitly.
- No writes were made to `D:/onedrive/Documents/GitHub/aspose.org`.
- No writes were made to `D:/onedrive/Documents/GitHub/aspose.org/content`.

## Repository Map - aspose.org

Role: Hugo website repo and embedded reference implementation for the skills system.

Observed root surfaces:

- Governance and agent instructions: `AGENTS.md`, `CODEX.md`, `CLAUDE.md`, `.kilocode/rules-code/`, `docs/governance/`, `docs/workflows/`, `docs/registries/`.
- Canonical or provider skill trees:
  - `.agents/skills/*/SKILL.md`
  - `.kilocode/skills/*/SKILL.md`
  - `.claude/commands/*.md`
  - `skills/*.md`
  - `skills/registry.json` where present.
- Backing implementation:
  - `scripts/pipeline/commands/` across content, diagnostics, enrichment, governance, healing, knowledge, launch, migration, ops, and KiloCode domains.
  - `scripts/pipeline/content_eval/`, `scripts/pipeline/lib/`, `scripts/pipeline/core/`, `scripts/gap-eval/`, `scripts/translator/`.
  - `scripts/ci/checks/`, `scripts/ci/hooks/`, `scripts/ci/tests/`.
- CI and governance workflows: `.github/workflows/ci-eval-consistency.yml`, `content-audit.yml`, `extraction-pipeline.yml`, `skill-governance.yml`.
- Runtime/source dependencies: `knowledge/`, `runs/.clone_cache/`, `content/`, `themes/`, `layouts/`, `configs/`, `data/`, `reports/`, `backlog/`, `plans/`, `repairs/`.

Current evidence:

- `.agents/skills` has 84 top-level skill directories.
- `.kilocode/skills` has 84 top-level skill directories.
- `.agents/skills` and `.kilocode/skills` have matching top-level skill names.
- `.claude/commands` has 77 top-level markdown command files.
- `skills/` has 85 top-level markdown files.
- Names present in aspose.org but absent from standalone `.agents/skills`: `blog-migrate`, `pipeline-harden`.

Likely source-of-truth surfaces for deeper inventory:

- Formal registry and catalog: `skills/registry.json`, `skills/*.md`, `skills/README.md`.
- Provider mirrors: `.agents/skills/*/SKILL.md`, `.kilocode/skills/*/SKILL.md`, `.claude/commands/*.md`.
- Registry and provider generation: `scripts/pipeline/commands/ops/sync_providers.py`, `scripts/pipeline/commands/ops/sync_skills.py`, and skill registry validation checks under `scripts/ci/checks/`.
- Execution backing: every script/module mentioned by a skill file, registry entry, command file, workflow, or governance rule.
- Governance backing: path guards, evidence gates, no-downgrade checks, skill-context checks, proof-bundle checks, launch/readiness checks, CI hooks, and docs under `docs/governance/`, `docs/workflows/`, and `docs/registries/`.

## Repository Map - foss-launcher-skills-gitlab

Role: standalone skills repository intended to provide a cleaner, better organized, better documented, better governed, and better maintained representation of the same practical skills system.

Observed root surfaces:

- Governance and agent instructions: `AGENTS.md`, `AGENTS.template.md`, `CODEX.md`, `CLAUDE.md`, `CONVENTIONS.md`, `OPERATOR_GUIDE.md`, `QUICKSTART.md`, `README.md`, `docs/RUNBOOK.md`.
- Canonical or provider skill trees:
  - `.agents/skills/*/SKILL.md`
  - `.kilocode/skills/*/SKILL.md`
  - `.claude/commands/*.md`
  - `skills/*.md`
  - `skills/registry.yaml`
- Backing implementation:
  - `scripts/pipeline/commands/` across content, diagnostics, governance, healing, knowledge, launch, ops, and related domains.
  - `scripts/pipeline/config/registry.yaml`.
  - `scripts/translator/tests/` and standalone `tests/`.
  - Top-level standalone utilities such as `apply.py`, `safety.py`, and `check-blog-slugs.py` are present in the worktree and require Phase 3 classification.
- CI and governance workflows: `.github/workflows/eval-consistency.yml`, `pipeline-tests.yml`, `skill-governance.yml`, `skill-registry-audit.yml`, plus `.gitlab-ci.yml`.
- Runtime/source dependencies: `config.yaml`, `configs/`, `knowledge/`, `golden/`, `repos/`, `runs/`, `output/`, `intake/`, `reports/`, `tools/`, `evidence/`.
- Historical parity program: `docs/parity/` contains prior inventories, parity matrices, gap reports, target designs, taskcards, verification evidence, and helper tools.

Current evidence:

- `.agents/skills` has 92 top-level skill directories.
- `.kilocode/skills` has 92 top-level skill directories.
- `.agents/skills` and `.kilocode/skills` have matching top-level skill names.
- `.claude/commands` has 85 top-level markdown command files.
- `skills/` has 92 top-level markdown files.
- Names present in standalone but absent from aspose.org `.agents/skills`: `corpus-scan`, `discover-products`, `evidence-decide`, `evidence-materialize`, `evidence-verify`, `ground-check`, `mental-model`, `seo-review`, `translate`, `truth-sync`.
- Existing `docs/parity/README.md` says a prior parity program was complete as of 2026-04-27, but the current skill counts no longer match that README. Treat it as historical, not authoritative.
- Current standalone git status is dirty with many modified and untracked files, including registry, scripts, tests, skills, and reports. Phase 2+ must avoid overwriting unrelated work and must classify these files as current state, historical migration residue, or pending implementation evidence.

Likely source-of-truth surfaces for deeper inventory:

- Formal registry: `skills/registry.yaml`.
- Canonical catalog: `skills/*.md`.
- Provider mirrors: `.agents/skills/*/SKILL.md`, `.kilocode/skills/*/SKILL.md`, `.claude/commands/*.md`.
- Registry and provider sync: validation and sync tests under `tests/`, scripts referenced by `skills/registry.yaml`, and any sync tooling found in `scripts/`.
- Execution backing: every registry-bound script and every path mentioned in skill text, provider mirrors, docs, workflows, and tests.
- Governance backing: `AGENTS.md`, `CONVENTIONS.md`, CI workflows, `.gitlab-ci.yml`, tests, hooks, config loaders, path guards, no-downgrade checks, content-repo adapters, and non-destructive verification fixtures.
- Prior parity tooling: `docs/parity/tools/extract_skill_inventory.py`, `compare_skill_parity.py`, `check_registry_scripts.py`. These are candidate tools for reuse after validating against current schemas and repo state.

## Normalized Skill Inventory Schema

Each skill or capability record in Phases 2 and 3 will use this schema:

```yaml
canonical_name:
aliases:
repo:
repo_path:
provider_paths:
  canonical_markdown:
  codex_skill:
  claude_command:
  kilocode_skill:
  registry_entry:
role_purpose:
skill_id:
parent_child_relationships:
feature_group:
trigger_invocation:
inputs:
outputs:
side_effects:
write_paths:
forbidden_paths:
generated_artifacts:
dependencies:
  skills:
  scripts:
  modules:
  configs:
  docs_contracts:
  templates:
  snippets:
  prompt_fragments:
  shared_libraries:
  tests:
  fixtures:
  external_tools:
  repo_layout:
  content_layout:
  theme_layout:
  knowledge_store:
  clone_cache:
  runtime_cache:
config_keys:
required_environment:
governance_hooks:
ci_references:
entrypoints:
dry_run_support:
redirected_output_support:
runtime_state:
source_of_truth_files:
maturity_status:
feature_status:
verification_status:
maintainability_notes:
evidence:
  files:
  line_refs:
  commands:
  command_outputs:
  hashes:
confidence:
ambiguities:
notes:
```

Each repository-level inventory will also capture:

```yaml
repo:
role:
current_git_status_summary:
skill_tree_counts:
registries:
provider_mirrors:
operator_docs:
governance_docs:
script_roots:
test_roots:
fixture_roots:
template_roots:
snippet_roots:
ci_workflows:
hooks:
runtime_data_roots:
content_or_external_repo_coupling:
known_forbidden_write_paths:
known_output_roots:
known_discovery_mechanisms:
known_sync_mechanisms:
known_validation_mechanisms:
historical_parity_artifacts:
inventory_completeness_checks:
```

## Behavior-First Equivalence Method

Same file names or same skill names are only weak hints. A standalone capability will be considered present only if it can achieve the same practical user outcome with equivalent or better execution coverage, reliability, discoverability, governance, documentation, configurability, testability, and maintainability.

Phase 4 will compare capabilities in this order:

1. Identity and discoverability: slug, aliases, skill ID, registry entry, provider mirrors, command availability, hidden/internal status, and operator-facing docs.
2. User outcome: what the skill lets an operator actually do, including required inputs, produced artifacts, side effects, and expected workflow position.
3. Contract behavior: prerequisites, hard stops, write paths, forbidden paths, dry-run behavior, redirected output behavior, generated artifacts, and rollback expectations.
4. Backing implementation: scripts, modules, helper utilities, CLI flags, config keys, environment variables, shared libraries, templates, snippets, and expected repo layout.
5. Governance behavior: path guard, evidence guard, no-downgrade guard, content-write guard, registry validation, proof bundle, launch readiness, shell policy, and CI/hook enforcement.
6. Verification behavior: unit tests, fixture tests, smoke tests, dry-run tests, negative tests, docs-to-code consistency tests, and safety tests proving no writes to `aspose.org/content`.
7. Maintainability improvement: whether standalone implements the same behavior with cleaner structure, clearer registration, better docs, stronger tests, or lower coupling.

Allowed Phase 4 parity statuses:

- exact parity proven
- functional parity proven through different implementation
- partial parity
- governance-only present
- documented but not implemented
- implemented but not registered/discoverable
- implemented but not verified
- missing entirely
- unclear, requires investigation

Allowed gap classifications:

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

- Assumption A1: Existing `docs/parity/` artifacts can be used as historical inputs, but not as proof of current parity. Evidence: current counts differ from `docs/parity/README.md`.
- Assumption A2: `.agents/skills` and `.kilocode/skills` are provider mirrors, not independently authoritative skill definitions. Evidence: top-level names match within each repo, but registry/catalog files also exist and may drive generation.
- Assumption A3: `aspose.org` is the reference behavior source even when standalone has more skill names. Evidence: user instruction names `aspose.org` as Source set A/reference implementation and standalone as target clean implementation.
- Assumption A4: A skill prompt without its backing scripts, config, tests, and governance is not functionally present. Evidence: user explicitly states not to assume a skill is present because a prompt file exists.

## Unresolved Ambiguities

- Whether `blog-migrate` and `pipeline-harden` are intentionally excluded from standalone or are true missing capabilities.
- Whether standalone-only skills are genuine improvements, renamed aspose capabilities, or partial migration residue.
- Whether dirty/untracked standalone files represent accepted current implementation, work in progress, or artifacts that must be folded into the refreshed parity program.
- Whether prior parity tools fully cover the expanded schema required by this refreshed run; they must be reviewed before reuse.
- Whether `.claude/commands` count differences are intentional internal-skill hiding or missing command registration.

## Phase 1 Decisions

- Use Git for Windows Bash explicitly for governed local operations.
- Treat all prior `docs/parity/` reports as historical evidence until refreshed by current inventories.
- Use behavior-first equivalence; never declare parity from matching file names alone.
- Place all new parity artifacts in standalone `docs/parity/` unless a later phase documents a stronger location.
- Do not write to any path under `D:/onedrive/Documents/GitHub/aspose.org`.

## Next Phase Entry Criteria

Phase 2 may begin when:

- This Phase 1 artifact is accepted as the current reconnaissance baseline.
- Inventory extraction is run read-only against `aspose.org`.
- The extraction captures both explicit skill files and hidden dependencies in scripts, docs, registries, hooks, CI, config, tests, and generated-artifact conventions.

