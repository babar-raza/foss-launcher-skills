# CLI Reference

Status: Current
Audience: Operator, Contributor, Agent
Canonical reference: this page
Last code-backed audit: 2026-05-30

This page owns command and flag reference extracted from the code audit. Guides link here instead of duplicating full option lists.

## Scout

Entrypoint: `scripts/pipeline/commands/knowledge/scout.py`

Purpose: tree-sitter extraction of API surface, formats, limitations, snippets, and claims from a FOSS repository.

```bash
python scripts/pipeline/commands/knowledge/scout.py FAMILY PLATFORM REPO_PATH OUTPUT_DIR [--preflight] [-v|--verbose]
```

Arguments and flags:

| Name | Type | Purpose |
|---|---|---|
| `family` | positional | Product family. |
| `platform` | positional | Target platform; constrained by supported platform map in code. |
| `repo_path` | positional path | FOSS repository path. |
| `output_dir` | positional path | Directory for extraction artifacts. |
| `--preflight` | flag | Check prerequisites without extraction. |
| `-v`, `--verbose` | flag | Enable debug logging. |

## Content Eval

Entrypoint: `scripts/pipeline/content_eval/cli.py`

Preferred invocation: use package/module invocation or the wrapper named by the command error message; direct `cli.py` execution exits with guidance.

Commands:

| Command | Purpose |
|---|---|
| `evaluate` | Run evaluation pipeline. |
| `diff` | Compare two evaluation reports. |
| `grade-summary` | Show grade distribution. |

`evaluate` flags:

| Flag | Purpose |
|---|---|
| `target` | Optional product/family/all target. |
| `--files` | Specific files to evaluate. |
| `--evaluators` | Comma-separated evaluator names. |
| `--format` | `markdown` or `json`. |
| `--strict` | Exit non-zero on FAIL findings. |
| `--dry-run` | Print what would be evaluated. |
| `--cross-page` | Enable cross-page analysis. |
| `--remediation` | Include remediation plan. |
| `--output-root` | Override report root. |
| `--write-grade` | Force grade writes. |
| `--write-grade-if-policy-met` | Write grades only when policy allows. |
| `--skip-graded` | Skip pages already graded with current knowledge. |
| `--sweep` | Sweep all products for same defect classes. |

## Path Guard

Entrypoint: `scripts/pipeline/commands/governance/path_guard.py`

```bash
python scripts/pipeline/commands/governance/path_guard.py PATH [--json]
python scripts/pipeline/commands/governance/path_guard.py --stdin [--json]
```

Exit codes:

| Code | Meaning |
|---:|---|
| 0 | Allow. |
| 2 | Deny. |

## Preflight

Entrypoint: `scripts/pipeline/commands/launch/preflight.py`

```bash
python scripts/pipeline/commands/launch/preflight.py PATH [--json]
```

Checks:

1. Path guard.
2. Python placement.
3. Content workflow marker for `content/` paths.

## Batch Reference

Entrypoint: `scripts/pipeline/commands/content/batch_reference.py`

```bash
python scripts/pipeline/commands/content/batch_reference.py FAMILY PLATFORM [options]
```

Key options:

| Option | Purpose |
|---|---|
| `--kind {class,enum,all}` | Filter API entries. |
| `--limit N` | Limit processed entries. |
| `--dry-run` | Preview without writes. |
| `--update` | Regenerate pages for modified APIs from `knowledge_delta.json`. |
| `--require-member-doc-coverage N` | Abort below member-doc coverage percentage. |
| `--heal` | Healing mode for auto-updatable pages. |
| `--confirm-heal` | Confirmation for broad healing. |
| `--rebuild-all` | Regenerate existing auto-updatable reference pages. |
| `--confirm-rebuild` | Confirmation for broad rebuild. |
| `--plan PATH` | Use site plan for advisory comparison. |
| `--generate-index` | Generate grouped reference `_index.md`. |
| `--knowledge-root DIR` | Override knowledge root. |
| `--content-root DIR` | Override reference content root. |

## Site Planner

Entrypoint: `scripts/pipeline/commands/launch/site_planner.py`

```bash
python scripts/pipeline/commands/launch/site_planner.py FAMILY PLATFORM [options]
```

Options:

| Option | Purpose |
|---|---|
| `--mode {launch,update,section}` | Planning mode. |
| `--section {products,docs,blog,kb,reference}` | Section mode target. |
| `--dry-run` | Print plan YAML to stdout. |
| `--detect-clusters` | Print cluster JSON and exit. |
| `--replan-blog` | Opt-in replacement of legacy generated features blog slugs. |

## Repo Patrol

Entrypoint: `scripts/pipeline/commands/diagnostics/repo_patrol.py`

```bash
python scripts/pipeline/commands/diagnostics/repo_patrol.py scan [options]
python scripts/pipeline/commands/diagnostics/repo_patrol.py sweep
python scripts/pipeline/commands/diagnostics/repo_patrol.py report
```

`scan` options:

| Option | Purpose |
|---|---|
| `--apply` | Write discovered candidates to product registry. |
| `--inactive-days N` | Inactivity threshold. |
| `--force` | Re-evaluate rejected repos. |
| `--orgs CSV` | Override default org list. |
| `--token TOKEN` | GitHub token; otherwise code falls back to environment. |

## Session Logger

Entrypoint: `scripts/pipeline/commands/ops/session_logger.py`

```bash
python scripts/pipeline/commands/ops/session_logger.py log --skill S-XX [--name NAME] [--exit-code N] [--verified] [--args ...]
python scripts/pipeline/commands/ops/session_logger.py show
```

Records are written to `reports/session-invocations/`.

## Override Manager

Entrypoint: `scripts/pipeline/commands/governance/override_manager.py`

Commands:

| Command | Purpose |
|---|---|
| `create` | Create pending override token. |
| `validate-for-path` | Check pending token coverage for a path. |
| `consume` | Archive a token after commit. |
| `list-pending` | List pending tokens. |
| `audit` | List archived tokens. |

Operator-only use. General guides should not route agents through override mechanics.
