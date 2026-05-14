# Review Package - 2026-05-14 Parity Resume

## Purpose

Provide a review/staging map for the May 13 parity sprint resume. This file separates durable parity deliverables from generated/runtime outputs and suggests commit-sized groups.

## Current Verification Baseline

```text
Final parity: 84/84 functional parity proven through different implementation
Gap categories: {}
Standalone-only preserved: 8
Full suite: 738 passed, 15 skipped
Skill registry: PASS (92 skills, 7 internal, no violations)
Provider sync: PASS for .agents/.kilocode/.claude
aspose.org/content final diff: none for the inspected content file
Top-level utility contracts: PASS for apply.py --help, safety.py --help, and check-blog-slugs.py fixture validation
```

## Recommended Commit Groups

### Commit 1 - Skill Registry And Surface Additions

Purpose: Make the three compatibility/governance skill surfaces discoverable.

Files:

- `README.md`
- `skills/registry.yaml`
- `skills/translate.md`
- `skills/content-enrich.md`
- `skills/seo-review.md`
- `.agents/skills/translate/SKILL.md`
- `.agents/skills/content-enrich/SKILL.md`
- `.agents/skills/seo-review/SKILL.md`
- `.kilocode/skills/translate/SKILL.md`
- `.kilocode/skills/content-enrich/SKILL.md`
- `.kilocode/skills/seo-review/SKILL.md`
- `.claude/commands/translate.md`
- `.claude/commands/content-enrich.md`
- `.claude/commands/seo-review.md`

Validation:

```bash
python scripts/validate_skills.py
python scripts/sync_agents.py --check
python scripts/sync_commands.py --check
```

### Commit 2 - Standalone Adapter And Helper Ports

Purpose: Preserve aspose.org behavior through cleaner standalone helpers and compatibility wrappers.

Primary files:

- `scripts/content_repo_adapter.py`
- `scripts/pipeline/core/clone_cache.py`
- `scripts/pipeline/lib/grade_writer.py`
- `scripts/pipeline/lib/heal_controller.py`
- `scripts/pipeline/commands/governance/skill_context.py`
- `scripts/pipeline/commands/content/validate_frontmatter.py`
- `scripts/pipeline/commands/content/batch_reference.py`
- `scripts/pipeline/commands/content/ground_check.py`
- `scripts/pipeline/commands/content/validate_plugin_structure.py`
- `scripts/pipeline/commands/content/cross_platform_audit.py`
- `scripts/pipeline/commands/enrichment/`
- `scripts/pipeline/commands/diagnostics/repo_patrol.py`
- `scripts/pipeline/commands/diagnostics/smoke_test.py`
- `scripts/pipeline/commands/diagnostics/truth_audit_content.py`
- `scripts/pipeline/commands/governance/check_graded_at_only.py`
- `scripts/pipeline/commands/healing/retire_page.py`
- `scripts/pipeline/commands/launch/launch_rollback.py`
- `scripts/pipeline/commands/launch/readiness_scorecard.py`
- `scripts/pipeline/commands/ops/link_validator.py`
- `scripts/pipeline/commands/ops/page_impact_assess.py`
- `scripts/pipeline/commands/ops/project_phase_store.py`
- `scripts/pipeline/commands/ops/refresh_review.py`
- `scripts/pipeline/commands/ops/sync_skills.py`
- `scripts/pipeline/extraction/`
- `scripts/pipeline/commands/migration/`
- `scripts/pipeline/repo_patrol.py`
- `scripts/pipeline/smoke_test.py`
- `scripts/pipeline/validate_plugin_structure.py`
- `scripts/pipeline/complete_plugin_structure.py`
- `scripts/gap-eval/`
- `scripts/seo/`
- `apply.py`
- `safety.py`
- `check-blog-slugs.py`

Resume-specific repair:

- `scripts/pipeline/commands/content/audit.py`
- `scripts/pipeline/commands/content/remediate.py`

Validation:

```bash
python -m pytest -q
python scripts/pipeline/commands/content/audit.py --help
python scripts/pipeline/commands/content/remediate.py --help
python apply.py --help
python safety.py --help
python check-blog-slugs.py --content-root tests/fixtures/content
```

### Commit 3 - Tests

Purpose: Add focused regression coverage for the migrated helpers and verification contracts.

Files:

- `tests/test_batch_reference.py`
- `tests/test_clone_cache.py`
- `tests/test_content_enrich_scaffold.py`
- `tests/test_content_repo_adapter.py`
- `tests/test_cross_platform_and_enrich.py`
- `tests/test_cross_platform_audit.py`
- `tests/test_final_helper_contracts.py`
- `tests/test_gap_eval_helpers.py`
- `tests/test_gap_eval_scaffold.py`
- `tests/test_governance_checks.py`
- `tests/test_grade_churn_guards.py`
- `tests/test_grade_writer.py`
- `tests/test_ground_check.py`
- `tests/test_healing_refresh_helpers.py`
- `tests/test_maintenance_truth_sync_helpers.py`
- `tests/test_phase_readiness_rollback_link_tools.py`
- `tests/test_plugin_structure_tools.py`
- `tests/test_repo_patrol.py`
- `tests/test_seo_apply_helpers.py`
- `tests/test_skill_context.py`
- `tests/test_smoke_test.py`
- `tests/test_validate_frontmatter.py`
- `scripts/pipeline/tests/`

Validation:

```bash
python -m pytest -q
```

### Commit 4 - Parity Evidence And Governance Docs

Purpose: Make the parity proof durable and reviewable.

Files:

- `docs/parity/README.md`
- `docs/parity/closure-report.md`
- `docs/parity/closure-report-2026-05-14.md`
- `docs/parity/verification-log.md`
- `docs/parity/parity-matrix.md`
- `docs/parity/gap-report.md`
- `docs/parity/compatibility-path-map.json`
- `docs/parity/prompt-orchestration-map.json`
- `docs/parity/tools/`
- `docs/parity/design/`
- `docs/parity/verification/`
- `docs/parity/evidence/`
- `docs/parity/inventories/`
- `docs/parity/taskcards/`
- `docs/parity/target-state-migration-design.md`
- `docs/parity/target-state-migration-design.json`
- `docs/parity/taskcard-index.md`
- `docs/parity/gap-report-phase4.md`
- `docs/parity/parity-matrix-phase4.md`
- `docs/parity/parity-matrix-phase4.json`
- `docs/parity/phase1-reconnaissance-2026-05-13.md`
- `docs/parity/phase1-reconnaissance-2026-05-14.md`

Validation:

```bash
python docs/parity/tools/compare_skill_parity.py \
  --foss-inventory docs/parity/evidence/phase7-resume-foss-inventory.json \
  --out docs/parity/evidence/phase7-resume-parity-run-final.json
python docs/parity/tools/summarize_parity.py \
  docs/parity/evidence/phase7-resume-parity-run-final.json
```

## Generated Or Runtime Outputs To Review Before Staging

These are likely runtime outputs. Do not stage unless the reviewer wants sample artifacts committed.

- `reports/discovery/combined_report.md` currently contains an empty patrol/sweep report.

## Safety Notes

- Do not stage or commit anything from `D:/onedrive/Documents/GitHub/aspose.org`.
- `aspose.org/content/websites.aspose.org/en/aspose/org/_index.md` was restored to no diff during the resume.
- Before committing, re-run:

```bash
cd D:/onedrive/Documents/GitHub/aspose.org
git status --short -- content
```

Expected output: no content files.
