# Phase 1: Repository Reconnaissance Report

**Generated**: 2026-05-29
**Source A**: D:\onedrive\Documents\GitHub\aspose.org (Hugo website repo with embedded skills)
**Source B**: C:\Users\prora\OneDrive\Documents\GitHub\foss-launcher-skills-gitlab (standalone skills repo)

## Repo Map: aspose.org

### Skill System Locations
| Location | Purpose | File Count |
|----------|---------|------------|
| `skills/*.md` | Canonical skill source (84 files) | 84 |
| `.kilocode/skills/{name}/SKILL.md` | Kilo Code provider mirror | 84 |
| `.agents/skills/{name}/SKILL.md` | Codex CLI provider mirror | 84 |
| `.claude/commands/{name}.md` | Claude Code provider mirror (internal skills excluded) | 76 |

### Script/Pipeline Locations
| Location | Purpose | File Count |
|----------|---------|------------|
| `scripts/pipeline/commands/content/` | Content audit/validation | 5+ |
| `scripts/pipeline/commands/knowledge/` | Knowledge extraction | 5+ |
| `scripts/pipeline/commands/launch/` | Launch orchestration | 2+ |
| `scripts/pipeline/commands/ops/` | Operational tools | 40+ |
| `scripts/pipeline/commands/diagnostics/` | Diagnostic tools | 3+ |
| `scripts/pipeline/lib/` | Shared library modules | 19 |
| `scripts/pipeline/core/` | Core infrastructure | 10+ |
| `scripts/pipeline/content_eval/` | Content evaluation engine | 10+ |

### Governance/Documentation Locations
| Location | Purpose | File Count |
|----------|---------|------------|
| `AGENTS.md` | Main governance file (1247 lines) | 1 |
| `docs/governance/*.md` | Governance child docs | 10 |
| `docs/workflows/*.md` | Workflow docs | 12 |
| `docs/registries/*.md` | Registry documentation | 2 |
| `scripts/pipeline/requirements-ci.txt` | CI dependencies | 1 |

### CI Locations
| Location | Purpose |
|----------|---------|
| `.github/workflows/skill-governance.yml` | Skill governance CI (blocking) |
| `.github/workflows/metrics-governance.yml` | Metrics governance CI |
| `.github/workflows/extraction-pipeline.yml` | Knowledge extraction CI |
| `.github/workflows/content-audit.yml` | Content audit CI |
| `.github/workflows/ci-eval-consistency.yml` | Evaluator consistency CI |
| `.github/workflows/cross-repo-index-sync.yml` | Cross-repo sync CI |

### CI Checks
| Location | Count |
|----------|-------|
| `scripts/ci/checks/*.py` | 63 files |

## Repo Map: foss-launcher-skills-gitlab

### Skill System Locations
| Location | Purpose | File Count |
|----------|---------|------------|
| `skills/*.md` | Canonical skill source (92 files) | 92 |
| `skills/registry.yaml` | Machine-readable registry | 1 |
| `scripts/_skill_constants.py` | Internal skill constants | 1 |
| `.claude/commands/*.md` | Claude provider (via sync_commands.py) | Derived |
| `.agents/skills/`, `.kilocode/skills/` | Via sync_agents.py | Generated |

### Script/Pipeline Locations
| Location | Purpose | File Count |
|----------|---------|------------|
| `scripts/*.py` (root) | Pipeline entrypoints | 30+ |
| `scripts/pipeline/commands/*.py` | Skill commands | 15+ |
| `scripts/pipeline/lib/` | Shared libraries | 0 (MISSING) |
| `scripts/pipeline/core/` | Core infrastructure | 0 (MISSING) |
| `scripts/pipeline/content_eval/` | Content evaluation | 15+ |
| `scripts/pipeline/scout_enrichers/` | Scout enrichers | 3 |
| `scripts/gap-eval/` | Gap-eval subsystem | 5+ |
| `scripts/translator/` | Translation subsystem | 20+ |
| `scripts/ci/checks/*.py` | CI checks | 63 (partial list seen) |

### Governance/Documentation Locations
| Location | Purpose | File Count |
|----------|---------|------------|
| `AGENTS.md` | Main governance (1247 lines) | 1 |
| `AGENTS.template.md` | Governance template | 1 |
| `docs/governance/*.md` | Governance docs | 10 (partial) |
| `docs/workflows/*.md` | Workflow docs | 11 (partial) |
| `docs/id-mapping.md` | Skill ID mapping | 1 |

### CI Locations
| Location | Purpose |
|----------|---------|
| `.github/workflows/skill-governance.yml` | Skill governance CI |
| `.github/workflows/pipeline-tests.yml` | Pipeline tests CI |
| `.github/workflows/eval-consistency.yml` | Evaluator consistency CI |
| `.github/workflows/skill-registry-audit.yml` | Registry audit CI |

## Key Findings from Existing Inventory Work

Evidence from `reports/parity/` shows substantial prior analysis:

### Skill Count Comparison
| Metric | aspose.org | foss-launcher-skills-gitlab |
|--------|------------|---------------------------|
| Total skills | 84 | 92 |
| Internal skills | 8 | 6 |
| Skills with scripts | ~30 | ~30 |
| foss-only skills | - | 10 |
| aspose-only skills | 2 | - |

### Gap Classifications (from existing gap-report.md)
| Classification | Count |
|----------------|-------|
| missing_test_coverage | 59 |
| size_divergence | 52 |
| missing_governance | 33 |
| missing_dependency | 18 |
| missing_skill | 2 |
| documented_not_implemented | 1 |
| implemented_not_verified | 9 |

### Critical Findings Identified
1. **S-43 gap-eval portability barrier**: Hardcoded aspose.org content paths in `scripts/gap-eval/src/run.py`
2. **60/63 CI checks are portable** (3 are website-specific)
3. **scripts/pipeline/lib/** missing in foss-launcher (19 shared modules in aspose.org)

## Source-of-Truth Confirmation

| Aspect | aspose.org Source | foss-launcher Source |
|--------|-------------------|---------------------|
| Skill registry | AGENTS.md §12 + docs/registries/skills.md | skills/registry.yaml |
| Skill files | skills/*.md | skills/*.md |
| Internal skills | scripts/pipeline/lib/_skill_constants.py | scripts/_skill_constants.py |
| Skill sync | scripts/pipeline/commands/ops/sync_skills.py + sync_providers.py | scripts/sync_commands.py + sync_agents.py |

## Evidence Files Located

The following inventory artifacts already exist in foss-launcher-skills-gitlab:
- `reports/parity/aspose-inventory.yaml` (84 skills)
- `reports/parity/foss-inventory.yaml` (92 skills)
- `reports/parity/parity-matrix.md`
- `reports/parity/gap-report.md` (comprehensive gap analysis)
- `reports/parity/aspose-ci-checks-map.yaml` (63 CI checks)
- `reports/parity/foss-test-coverage-map.yaml`
- `reports/parity/target-architecture.md`
- `docs/id-mapping.md` (cross-reference)

## Phase 1 Exit Criteria Status

| Criterion | Status | Evidence |
|-----------|--------|----------|
| Defensible repo map exists | ✓ COMPLETE | This document + detailed file listings |
| All skill system surfaces identified | ✓ COMPLETE | Skills, scripts, governance, CI, checks mapped |

## Next Phase Recommendations

Proceed to Phase 2 to:
1. Verify existing inventories are current and complete
2. Identify what's missing from the existing analysis
3. Update inventories with fresh evidence if needed