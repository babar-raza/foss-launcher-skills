# Normalized Skill Inventory -- foss-launcher-skills-gitlab

**Repository:** `C:\Users\prora\OneDrive\Documents\GitHub\foss-launcher-skills-gitlab`
**Registry:** `skills/registry.yaml` (YAML, schema v1)
**Total skills:** 88 (7 internal, 81 user-callable)
**ID range:** S-01 to S-105 with gaps (S-02-09, S-11, S-16, S-27-29, S-80, S-89, S-91-92)
**Evidence date:** 2026-04-27 (updated: added S-56 through S-105; infrastructure reassessed)

---

## Internal Skills (7)

Auto-invoked sub-routines excluded from `.claude/commands/`. Marked `internal: true` in `skills/registry.yaml`.

| foss ID | Slug | Description |
|---------|------|-------------|
| S-01 | path-guard | Enforced automatically on every write |
| S-10 | project-phase-store | Checkpoint infrastructure |
| S-17 | rubric-align | Sub-evaluator called by eval-page |
| S-24 | evidence-cite | Auto-invoked by generation skills |
| S-33 | change-guard | Auto-invoked before writes |
| S-49 | knowledge-bootstrap | Auto-invoked pre-condition gate |
| S-56 | no-downgrade-guard | Pre-write quality comparison; returns ALLOW/WARN/BLOCK |

---

## Full Skill Registry (84 skills)

| foss ID | Slug | Description | Internal | Script |
|---------|------|-------------|----------|--------|
| S-01 | path-guard | Enforce allowed write paths | YES | `scripts/path_guard.py` |
| S-10 | project-phase-store | Record page creation intent as a YAML plan file | YES | -- |
| S-12 | knowledge-diff | Detect upstream repo changes since last knowledge extraction | NO | -- |
| S-13 | stale-detect | Identify content pages affected by upstream changes | NO | -- |
| S-14 | knowledge-update | Refresh knowledge model from source repo | NO | `scripts/pipeline/refresh_knowledge.py` |
| S-15 | embed-knowledge | Generate vector embeddings for knowledge retrieval | NO | `scripts/embed.py` |
| S-17 | rubric-align | Align content to quality rubric and identify gaps | YES | -- |
| S-18 | page-plan | Plan page structure before drafting | NO | -- |
| S-19 | page-draft | Draft initial page content from knowledge model | NO | -- |
| S-20 | page-update | Update page after knowledge model change | NO | -- |
| S-21 | page-enhance | Enhance page quality to meet rubric bar | NO | -- |
| S-22 | faq-generate | Generate FAQ section from knowledge model | NO | -- |
| S-23 | ground-check | Pre-write evidence verification gate | NO | `scripts/pipeline/audit.py` |
| S-24 | evidence-cite | Attach evidence citations to content frontmatter | YES | `scripts/pipeline/attach_evidence.py` |
| S-25 | eval-page | Evaluate page quality and assign A-F grade | NO | `scripts/pipeline/content_eval/__main__.py` |
| S-26 | heal-page | Fix low-quality page to reach passing grade | NO | -- |
| S-30 | truth-sync | Import external FOSS-Launcher knowledge into fl/ | NO | -- |
| S-31 | truth-index | Generate knowledge index from merged artifacts | NO | `scripts/index.py` |
| S-32 | content-audit | Semantic knowledge verification of content pages | NO | `scripts/pipeline/content_audit.py` |
| S-33 | change-guard | Pre-write knowledge gate for single text blocks | YES | `scripts/pipeline/change_guard.py` |
| S-34 | repo-scout | Extract API truth from FOSS repository | NO | `scripts/scout.py` |
| S-35 | truth-merge | Merge scout and external knowledge sources | NO | `scripts/merge.py` |
| S-36 | cross-platform | Family-wide consistency check across platforms | NO | -- |
| S-37 | corpus-scan | Build golden corpus profile for a site type | NO | `scripts/corpus_scan.py` |
| S-38 | launch-product | Orchestrate full FOSS product launch end-to-end | NO | -- |
| S-39 | discover-products | Scan GitHub org to discover FOSS product repos | NO | `scripts/discover.py` |
| S-40 | batch-remediate | Full eval-to-fix-to-LLM-to-re-eval remediation pipeline | NO | `scripts/pipeline/remediate.py` |
| S-41 | batch-eval-fix | Quick eval plus deterministic auto-fix only (no LLM) | NO | `scripts/pipeline/remediate.py` |
| S-42 | category-fix | Run specific fixer on targeted files by category | NO | `scripts/pipeline/remediate.py` |
| S-43 | evidence-decide | Determine per-page content action from evidence | NO | `scripts/decide.py` |
| S-44 | evidence-materialize | Build canonical Product Evidence File from merged knowledge | NO | `scripts/materialize.py` |
| S-45 | mental-model | Build product mental model and capability tiers from PEF | NO | `scripts/mental_model.py` |
| S-46 | evidence-verify | Deterministic content verification against PEF | NO | `scripts/verify.py` |
| S-47 | truth-audit | Member-level API verification against knowledge surface | NO | -- |
| S-48 | content-eval | Multi-dimensional content evaluation against repo truth | NO | `scripts/pipeline/content_eval/__main__.py` |
| S-49 | knowledge-bootstrap | Shared pre-condition gate for knowledge state detection | YES | -- |
| S-50 | content-check | Structural and quality check on a content file pre-commit | NO | -- |
| S-51 | new-docs-page | Generate a new documentation page for docs.aspose.org | NO | -- |
| S-52 | new-blog-post | Generate a new blog post for blog.aspose.org | NO | -- |
| S-53 | new-kb-howto | Generate a new KB how-to article for kb.aspose.org | NO | -- |
| S-54 | new-kb-faq | Generate or update the FAQ page for a product platform | NO | -- |
| S-55 | new-reference-page | Generate a new API reference page for reference.aspose.org | NO | -- |
| S-56 | no-downgrade-guard | Pre-write quality comparison guard; ALLOW/WARN/BLOCK before writes | YES | `scripts/pipeline/no_downgrade_guard.py` |
| S-57 | site-plan | Produce deterministic evidence-bound site manifest across all 5 subdomains | NO | -- |
| S-58 | family-sync | Update family-level products page to reflect all launched platforms | NO | -- |
| S-59 | refresh-product-page | Re-generate products.aspose.org landing page via full S-66 pipeline | NO | -- |
| S-60 | launch-rollback | Revert one product's generated content files to last committed state | NO | -- |
| S-61 | knowledge-enrich | Generate LLM-enriched semantic claims from scout artifacts; writes enriched_claims.json | NO | -- |
| S-62 | gap-eval | Evaluate content against clone cache ground truth; produces PUBLICATION READY verdict | NO | -- |
| S-63 | gap-plan | Convert gap-eval findings into wave-ordered remediation plan with old-new substitutions | NO | -- |
| S-64 | gap-report | Synthesize gap-eval findings across all products into cross-product MASTER-SYNTHESIS | NO | -- |
| S-65 | gap-apply | Execute wave-ordered fix specs from gap-plan; Wave 1 auto-fixes through Wave 4 escalation | NO | -- |
| S-66 | new-products-page | Generate or update the products.aspose.org landing page for a FOSS product | NO | -- |
| S-67 | batch-reference | Generate reference pages in bulk for all missing classes/enums in a family+platform | NO | -- |
| S-68 | code-smoke | Syntax and type-check Python code blocks in content pages; never executes code | NO | -- |
| S-69 | getting-started | Bootstrap the repo environment from a fresh clone to a content-ready state | NO | -- |
| S-70 | link-validate | Validate cross-subdomain internal links; reports BROKEN links where target slug missing | NO | -- |
| S-71 | register-human-content | Onboard human-authored content pages into quality and provenance systems | NO | -- |
| S-72 | diagnose-skill-failure | Governed diagnostic; classifies failures as CONFIG/DATA/CODE/GOVERNANCE/REGRESSION | NO | -- |
| S-73 | update-registry | Discover and register FOSS repositories from Aspose GitHub organisations | NO | -- |
| S-74 | new-kb-index | Scaffold or repair KB platform section landing page with required frontmatter | NO | -- |
| S-75 | new-docs-index | Scaffold or repair docs platform section landing page with required frontmatter | NO | -- |
| S-76 | new-reference-index | Scaffold or repair reference platform section landing page with required frontmatter | NO | -- |
| S-77 | evidence-repair | Repair evidence frontmatter on validator-blocked pages; auto-attach then LLM reasoning | NO | -- |
| S-78 | manual-edit | Apply operator-directed targeted content edit under full governance | NO | -- |
| S-79 | causal-backtrack | Resolve upstream dependency failures by tracing to root cause | NO | -- |
| S-81 | commit | Stage and commit working tree changes with structured conventional commits | NO | -- |
| S-82 | session-start | Mandatory session initialization gate; reads governance + loads backlog | NO | -- |
| S-83 | evidence-enhance | Improve section-level evidence coverage on passing pages | NO | -- |
| S-84 | refresh-product | Orchestrate full post-launch product refresh; 14-step chain with checkpoint resume | NO | -- |
| S-85 | coverage-reconcile | Full disposition table for every knowledge unit (used/stored/orphaned/excluded) | NO | -- |
| S-86 | knowledge-coverage-audit | Per-claim disposition table; foundational observability for no-silent-knowledge-loss | NO | -- |
| S-87 | delta-site-plan | Incremental site planning after knowledge update; produces add/update/remove delta | NO | -- |
| S-88 | page-retire | Retire obsolete content pages via draft:true; preserves history and allows rollback | NO | -- |
| S-90 | truth-audit-content | Line-level content truth audit; decomposes pages and verifies each against knowledge model | NO | -- |
| S-93 | system-heal | Audit-driven content healing; classifies as CONTENT/PIPELINE/KNOWLEDGE and heals automatically | NO | -- |
| S-94 | heal-batch | Batch healing from content_eval report; routes findings to auto/LLM/regen heal modes | NO | -- |
| S-95 | publish-readiness-review | Agent-executed governed inspection; replaces human-review dead-ends with bounded verdict | NO | -- |
| S-96 | plan-normalize | Execution-safe plan quality gate; classifies sections, verifies claims, recommends next item | NO | -- |
| S-97 | triage-confirm | Layer 2 body-prose staleness scanner; detects stale API refs and orphaned claims; read-only | NO | -- |
| S-98 | backlog | Unified backlog management with 22 subcommands; durable planning state across sessions | NO | -- |
| S-99 | translate-page | Translate single English content page to target locales; preserves evidence and code blocks | NO | -- |
| S-100 | translate-batch | Batch translate all English content pages for a family/platform to target locales | NO | -- |
| S-102 | repo-patrol | Scan GitHub orgs for new FOSS repos, score confidence, produce patrol_report.json | NO | -- (repo_patrol.py pending port) |
| S-103 | change-sweep | Batch SHA comparison across all active products, produce sweep_report.json; read-only | NO | -- (repo_patrol.py pending port) |
| S-104 | discovery-triage | Route patrol/sweep reports to backlog actions; never directly invokes S-12 or S-84 | NO | -- |
| S-105 | section-enhance | Inspect any content section, detect gaps, produce read-only proposal pack | NO | -- |
| S-101 | locale-patch | Propagate targeted text fixes from English source to all locale translation copies | NO | -- |

---

## Capabilities Unique to foss-launcher (not in aspose.org)

These capabilities must be preserved and not regressed during migration:

| Slug/Component | foss ID | Description | Why Better |
|----------------|---------|-------------|------------|
| truth-sync | S-30 | Import external knowledge into fl/ subdirectory | No aspose equivalent |
| discover-products | S-39 | GitHub org scanner for FOSS repo discovery | Different approach from aspose update-registry |
| evidence-decide | S-43 | Per-page content action engine from PEF | Systematic evidence-driven workflow not in aspose |
| evidence-materialize | S-44 | Canonical Product Evidence File builder | aspose has no PEF concept |
| mental-model | S-45 | Capability tier + gap analysis from PEF | aspose has no mental-model skill |
| evidence-verify | S-46 | Deterministic PEF-grounded verification | More systematic than aspose gap-eval |
| corpus-scan | S-37 | Golden corpus profile for style anchoring | Different purpose from aspose knowledge-enrich |
| ground-check | S-23 | Evidence verification gate | foss splits structural/evidence; aspose combines in content-check |
| content-check | S-50 | Structural pre-commit check | Better distinguished from evidence check |
| content_eval module | S-48 | 16 evaluators + 8 auto-fixers | Richer than aspose evaluation |
| configs/schemas/ | -- | 6 JSON schemas for artifact validation | aspose has no schema validation |
| install.sh + install.ps1 | -- | Cross-platform installers | aspose has no installer |
| CODEX.md | -- | Codex CLI agent instructions | aspose has no CODEX.md |
| RBAC config | -- | scout/writer/reviewer/orchestrator roles | aspose has no RBAC |

---

## Infrastructure Summary

| Component | Present | Path / Notes |
|-----------|---------|------|
| Skill registry | YES | `skills/registry.yaml` (YAML -- better than JSON) |
| Sync scripts | YES | `scripts/sync_commands.py` + `scripts/sync_agents.py` (covers .agents/ and .kilocode/) |
| .claude/commands mirror | YES | 81 files (user-callable only; internal skills excluded) |
| .agents/skills mirror | YES | 88 directories |
| .kilocode/skills mirror | YES | 88 directories |
| Internal skill constant | YES | `scripts/_skill_constants.py` |
| GitHub CI workflows | YES | 1 workflow: `.github/workflows/skill-governance.yml` |
| Git hooks | YES | `scripts/pre-commit-audit.sh`, `scripts/commit-msg-skills.sh` |
| Hook installer | YES | `scripts/install-hooks.sh` |
| Translator system | NO | `scripts/translator/` absent; S-99/S-100/S-101 are prompt-only with no script backing |
| Gap-eval system | NO | Replaced by evidence pipeline; no run.py equivalent |
| SEO scripts | NO | Absent |
| CI validation scripts | YES | validate_skills.py, sync_commands.py, sync_agents.py, check_setup.py, readme_sync.py |
| Data directory | NO | Only `configs/families.yaml`; no products.json, platforms.json |
| RUNBOOK.md | YES | `docs/RUNBOOK.md` |
| OPERATOR_GUIDE.md | NO | Absent |
| Tests | YES | 37 test files in `tests/` + fixtures |
| Schema validation | YES | `configs/schemas/*.json` (6 schemas -- unique to foss) |
| Evidence pipeline | YES | `scripts/decide.py`, `materialize.py`, `verify.py`, `mental_model.py` |
| Install scripts | YES | `install.sh`, `install.ps1` |
| Distribution system | YES | `tools/distribute.py` |

---

## Key Structural Notes

1. **ID collisions resolved in registry header:**
   - S-38 collision: `launch-product` keeps S-38; `truth-audit` renumbered to S-47
   - S-42 collision: `category-fix` keeps S-42; `evidence-verify` renumbered to S-46

2. **Stale frontmatter IDs:** `truth-audit.md` has `id: S-38`; `evidence-verify.md` has `id: S-42` -- registry YAML is authoritative

3. **S-56+ IDs are foss-launcher-assigned** independently from aspose.org after parity program; cross-reference in `docs/id-mapping.md`

4. **Script coverage for S-56 to S-101:** Only `no_downgrade_guard.py` (S-56) has a backing script; all others are `script: null` (prompt-only ports)

5. **Translator skills (S-99, S-100, S-101)** are prompt-only ports; `scripts/translator/` package not yet ported (pending TC-P-01)

---

## Confidence Notes

- Registry data: HIGH (read directly from `skills/registry.yaml`)
- Script existence S-01 to S-55: HIGH (all confirmed present at last full verification)
- Script existence S-56 to S-101: HIGH (registry null = no script; no_downgrade_guard.py confirmed present)
- Internal skill set: HIGH (read from registry `internal: true` fields)
- Infrastructure state: HIGH (directory listing confirmed 2026-04-27)
- Skill content S-56 to S-101: MEDIUM (registry descriptions only; skill file bodies not individually verified)
