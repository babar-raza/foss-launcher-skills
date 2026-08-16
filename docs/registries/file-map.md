# File Map — §12 Content Paths, Environment & Scripts

> Source: AGENTS.md §12
> Status: Current (restored from archive 2026-06-24)

## Content Paths

| Path | Purpose |
|------|---------|
| `content/docs.aspose.org/en/{family}/{platform}/` | Per-platform documentation pages |
| `content/products.aspose.org/en/{family}/` | Family landing page (`layout: family`) — `/family-sync` |
| `content/products.aspose.org/en/{family}/{platform}/` | Platform product page (`layout: plugin`) |
| `content/kb.aspose.org/en/{family}/{platform}/` | KB how-to articles |
| `content/blog.aspose.org/{family}/{platform}/` | Blog posts (no `/en/` prefix) |
| `content/reference.aspose.org/en/{family}/{platform}/` | API reference index pages |

## Knowledge Artifacts

| Path | Purpose |
|------|---------|
| `knowledge/{family}/{platform}/merged/model.yaml` | Knowledge model + staleness flag (`stale_since`) |
| `knowledge/{family}/{platform}/merged/claims.json` | Structured evidence claims |
| `knowledge/{family}/{platform}/merged/api_surface.json` | API identifiers (scout output) |
| `knowledge/{family}/{platform}/merged/api_surface.md` | Public API surface — human-readable |
| `knowledge/{family}/{platform}/merged/formats.json` | Supported format claims |
| `knowledge/{family}/{platform}/snippets/` | Pre-approved code snippets |
| `runs/.clone_cache/{org}_{family}_{platform}/` | Local FOSS repo clone cache |

## Reports & Plans

| Path | Purpose |
|------|---------|
| `reports/plans/{family}/{platform}/site_plan.yaml` | Canonical site plan (from `/site-plan`) |
| `reports/skill-runs/` | Skill run audit records (JSON, gitignored) |
| `reports/human-review/` | H-gate sign-off files (required before READY TO SHIP) |
| `reports/eval-run/` | Evaluation outputs (content_eval, gap-eval, scorecard) |
| `reports/audit/` | Audit batch reports and quality baseline |
| `reports/audit/baseline-fail-counts.json` | Known pre-existing FAIL counts per product |
| `reports/overrides/pending/` | Pending forbidden-path override tokens |

## Key Scripts

| Script | Purpose |
|--------|---------|
| `scripts/pipeline/commands/content/audit.py` | Content truth audit |
| `scripts/pipeline/content_eval/cli.py` | Content quality evaluation |
| `scripts/gap-eval/src/run.py` | Gap analysis (Tier 1/2/3) |
| `scripts/pipeline/commands/launch/readiness_scorecard.py` | Ship-readiness scorecard |
| `scripts/pipeline/commands/launch/site_planner.py` | Site plan generation |
| `scripts/pipeline/commands/governance/skill_context.py` | Skill context gate |
| `scripts/pipeline/commands/ops/skill_run_manager.py` | Skill run record lifecycle |
| `scripts/translator/cli.py` | Translation CLI (audit, retranslate, preflight) |
| `scripts/pipeline/commands/ops/package_publish_watch.py` | Multi-registry (pypi/nuget/npm/go_modules/cargo) publish detection, `/package-publish-watch` (S-118) |
| `scripts/pipeline/commands/content/package_install_migrator.py` | Codemod: literal install commands → `package-install` shortcode |

## Data Files

| Path | Purpose |
|------|---------|
| `data/package_registry.json` | Unified package-manager identity SOT (Mission MT015-2026-07-30-PACKAGE-REGISTRY) — sole rendering source for the `maven-coord`/`maven-gav`/`cargo-crate`/`package-install` shortcodes; see `data/schemas/package-registry-schema.json` for shape. Supersedes the retired `data/foss_packages.json`/`data/cargo_packages.json` (deleted TC-MT015-14). |

## Environment

All scripts use `.venv/Scripts/python` (Windows) or `.venv/bin/python` (Unix/macOS).
Never use system Python — enforcement is via `scripts/ci/hooks/check_venv_bash_hook.sh`.

See [docs/STATUS-venv-closure.md](../STATUS-venv-closure.md) for the venv enforcement policy.

## Archive

Pre-refactor version:
[docs/_archive/pre-refactor/registries/file-map.md](../_archive/pre-refactor/registries/file-map.md)
