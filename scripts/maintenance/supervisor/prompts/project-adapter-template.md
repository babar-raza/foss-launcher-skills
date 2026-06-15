# PROJECT ADAPTER TEMPLATE

> Prompt ID: PSL-PA
> Version: 1.0.0

## Purpose

The project adapter configures the post-sprint autonomy loop for a specific project. It maps project-specific paths, commands, gates, and constraints so that the loop controller and prompt assets work without hardcoded assumptions.

## Required Fields

```yaml
# Project Adapter Configuration
adapter_version: "1.0.0"

project:
  name: ""                          # Human-readable project name
  repo_root: ""                     # Absolute path to repository root
  branch: ""                        # Default branch name

paths:
  evidence_dir: ""                  # Where stage outputs are written
  plan_dir: ""                      # Where plans are stored
  taskcard_dir: ""                  # Where taskcards are stored
  prompt_dir: ""                    # Where prompt assets live
  prompt_registry: ""               # Path to prompt-registry.yaml
  reports_dir: ""                   # Where reports are written
  supervisor_state_dir: ""          # Where supervisor state is persisted

commands:
  test: []                          # Commands to run tests
  validate: []                      # Commands to run validators
  build: []                         # Commands to build the project
  governance_check: []              # Commands to run governance checks
  lint: []                          # Commands to run linters

constraints:
  protected_paths: []               # Paths that must not be modified
  allowed_mutation_paths: []        # Paths where writes are allowed
  forbidden_actions: []             # Actions that must not be taken

docs:
  docs_paths: []                    # Documentation directories
  skills_paths: []                  # Skill definition directories
  agent_instruction_paths: []       # Agent instruction files

gates:
  project_specific_gates: []        # Project-specific quality gates
  external_blockers: []             # Known external blockers

packaging:
  final_package_format: "zip"       # Evidence bundle format
  evidence_bundle_path: ""          # Where evidence bundles are stored
```

## Adapter Discovery

The loop controller discovers the project adapter by:

1. Checking `--adapter` CLI argument
2. Checking `PSL_PROJECT_ADAPTER` environment variable
3. Looking for `project-adapter.yaml` in the prompt directory
4. Falling back to built-in defaults for the current project

## Validation Rules

An adapter is incomplete if any of these are true:

- `project.repo_root` is empty or does not exist
- `paths.evidence_dir` is empty
- `paths.prompt_dir` is empty
- `commands.test` is empty (no way to verify)
- `commands.validate` is empty (no way to validate)
- `constraints.allowed_mutation_paths` is empty (no safe write path)

An incomplete adapter blocks execution until repaired.

## Example: Aspose.org Adapter

See `project-adapter-aspose.yaml` for the concrete adapter for this repository.
