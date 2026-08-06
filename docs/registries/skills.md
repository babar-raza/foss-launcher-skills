# Skills Reference

> Canonical skill registry for AGENTS.md §12 governance coverage.
> This file is read by `test_skill_contract_paths.py::TestS12Completeness` to verify
> that every `skills/*.md` file is registered here.

### Skills reference

| Skill | ID | Purpose |
|-------|----|---------|
| backlog | S-88 | Unified backlog management and planning |
| batch-eval-fix | S-41 | Lightweight eval + deterministic auto-fixes only |
| batch-reference | S-62 | Bulk reference page generation |
| batch-remediate | S-40 | Full eval→fix→LLM→re-eval pipeline |
| blog-migrate | S-100 | Governed blog folder slug migration |
| category-fix | S-42 | Run specific fixer on files by category code |
| causal-backtrack | S-74 | Resolve upstream dependency failures |
| change-guard | S-33 | Pre-write knowledge gate |
| change-sweep | S-94 | Batch SHA comparison across all active products |
| cleanroom-regen | S-97 | Full cleanroom regeneration workflow |
| code-smoke | S-63 | Syntax and type-check code blocks |
| commit | S-76 | Full commit-prep workflow |
| content-audit | S-32 | Semantic knowledge verification |
| content-check | S-23 | Pre-write structural and quality check gate |
| content-enrich | S-98 | Post-launch cross-subdomain content enrichment |
| content-eval | S-51 | Multi-dimensional content evaluation |
| coverage-reconcile | S-80 | Trace knowledge units to page dispositions |
| cross-platform | S-36 | Family consistency check |
| delta-site-plan | S-82 | Incremental site planning after knowledge update |
| diagnose-skill-failure | S-67 | Governed diagnostic when a skill or pipeline script fails |
| discovery-triage | S-95 | Route patrol and sweep reports to backlog actions |
| embed-knowledge | S-15 | Embed knowledge artifacts into vector stores |
| eval-page | S-25 | Evaluate page grade |
| evidence-cite | S-24 | Attach knowledge citations to content pages |
| evidence-enhance | S-78 | Improve section evidence coverage on passing pages |
| evidence-repair | S-72 | Repair evidence frontmatter for validator-blocked pages |
| family-sync | S-48 | Update family-level products page |
| faq-generate | S-22 | Generate FAQ section |
| gap-apply | S-46 | Execute wave-ordered fix specs |
| grade-remediate | S-102 | Remediate D/F grade pages to meet the minimum quality bar |
| gap-eval | S-43 | Content verification against clone cache |
| gap-plan | S-44 | Wave-ordered remediation planning |
| gap-report | S-45 | Cross-product gap synthesis report |
| getting-started | S-64 | Fresh-clone onboarding |
| heal-batch | S-89 | Batch healing from content_eval report |
| heal-page | S-26 | Heal low-quality page |
| knowledge-bootstrap | S-54 | Pre-condition gate before content or validation |
| knowledge-coverage-audit | S-81 | Per-claim disposition table |
| knowledge-diff | S-12 | Detect upstream repo changes |
| knowledge-enrich | S-37 | LLM-enriched claims from scout api_surface |
| knowledge-update | S-14 | Refresh knowledge model from source |
| launch-product | S-49 | 5-subdomain full documentation launch orchestrator |
| launch-rollback | S-79 | Revert one product's generated content files |
| link-validate | S-65 | Validate cross-subdomain internal links |
| llms-coverage | S-LG-03 | Audit coverage gap between content and llms-output (gate: ≥95% per domain) |
| llms-fidelity | S-LG-04 | Audit content fidelity source vs output (gate: ≥90% overall score) |
| llms-generate | S-LG-01 | Regenerate all llms-output .txt files and llms.txt indexes for all 5 subdomains |
| llms-stale | S-LG-05 | Detect stale or missing llms-output .txt files via provenance manifest hash check |
| llms-verify | S-LG-02 | Verify live HTTP endpoints for deployed llms-output .txt pages |
| locale-patch | S-75 | Propagate targeted text fixes to locale files |
| manual-edit | S-73 | Operator-directed targeted content edit |
| mechanism-sweep | S-117 | Sweep already-launched products for staleness caused by OUR OWN pipeline (extraction/enrichment) improving, independent of any upstream FOSS change — the sibling of change-sweep's upstream-drift axis |
| new-blog-index | S-101 | Scaffold Blog platform section landing page |
| new-blog-post | S-57 | Generate blog posts for blog.aspose.org |
| new-docs-index | S-70 | Scaffold Docs platform section landing page |
| new-docs-page | S-56 | Generate documentation pages |
| new-kb-faq | S-59 | Generate or update FAQ page |
| new-kb-howto | S-58 | Generate KB how-to articles |
| new-kb-index | S-69 | Scaffold KB platform section landing page |
| new-products-page | S-61 | Generate products.aspose.org landing pages |
| new-reference-index | S-71 | Scaffold Reference platform section landing page ([index structure](../reference/reference-index-structure.md)) |
| new-reference-page | S-60 | Generate API reference pages |
| no-downgrade-guard | S-55 | Pre-write quality comparison sub-routine |
| page-draft | S-19 | Draft initial page content |
| page-enhance | S-21 | Enhance page to meet quality bar |
| page-plan | S-18 | Plan page structure |
| page-retire | S-83 | Retire obsolete content pages |
| page-update | S-20 | Update page after knowledge change |
| path-guard | S-01 | Enforce allowed write paths |
| pipeline-harden | S-99 | Parameterized pipeline hardening sprint |
| plan-normalize | S-91 | Execution-safe plan quality gate |
| post-sprint-loop | S-103 | Post-sprint autonomy loop: P1 audit → P2 plan-harden → P3 execute with auto-classify and retry |
| semantic-diff | S-104 | Converts knowledge_delta.json string arrays into typed semantic change objects; outputs semantic_changes.json |
| body-refresh | S-105 | Body prose refresh executor (CORE FIX); closes first failing boundary knowledge_delta.json → docs/KB/blog body prose; supports --dry-run and --execute; LLM callsite CS-015 |
| refresh-oracle | S-106 | Validates refreshed content against source truth; composes prose_stale_scan.py; queues missed cross-page propagation |
| locale-refresh-handoff | S-107 | Queues locale equivalents for re-translation; routes <3 sentences to S-75, >=3 to S-56 |
| frontmatter-body-consistency | S-108 | Checks paired-claim consistency between frontmatter evidence and body prose |
| production-localization-incident | S-109 | Production localization incident orchestration: containment, forensics, review packets, S-HT-01/S-HT-02/S-99 routing, deployment/live/CDN gates, monitoring, resume, and closeout |
| foss-java-publish | S-110 | Publish a FOSS Java library to Maven Central: surgical pom.xml patches, GHA tag-push automation, PUBLISHING.md runbook committed to product repo, and aspose.org English content healing with post-sweep verification |
| baseline-ledger-writer | S-111 | Append-only baseline SHA history per product + git-reachable baseline resolution with real orphaned-SHA walkback; replaces the mutable model.yaml.repo_sha scalar (RPR-C-01/03/04) |
| triage-verdict-gate | S-112 | Deterministic exit-code gate over triage_confirm/reconcile_triage findings; hard precondition for S-76 commit and post_refresh_verify Check 9 (RPR-F-03). Enforcement half of S-92 triage-confirm |
| plan-health-watchdog | S-113 | Detect stalled P0 taskcards and plan-prose contradicted by repo state via structured taskcards.jsonl (schema 5f) field comparison + plan-markdown parity check (RPR-G-04) |
| regression-classification | S-114 | Classify every grade regression JUSTIFIED/UNJUSTIFIED with a cited evidence source, writing the complete input list (never a sample) so it cannot be silently lost (RPR-A-01) |
| workflow-harden | S-115 | GitHub Actions CI forensic audit and hardening — trigger/permission/secret/cache correctness plus CI-weight reduction across `.github/workflows/**` |
| package-publish-watch | S-118 | Multi-registry (pypi/nuget/npm/go_modules/cargo) publish detection with 2-consecutive-check debounce + operator-confirmed content healing via package_install_migrator.py; Maven's own sibling is S-110/publish_watcher.py (Mission MT015-2026-07-30-PACKAGE-REGISTRY, TC-MT015-09) |
| media-optimize | S-119 | Rename static/media/{family}/{platform} product images to a fixed convention (icon.png/banner.png) and losslessly compress them under 1MB via oxipng, with per-file pixel-identity verification |
| project-phase-store | S-10 | Track generation phase state |
| publish-readiness-review | S-90 | Agent-executed governed inspection |
| refresh-product | S-84 | Full post-launch product refresh orchestration |
| refresh-product-page | S-86 | Re-generate a single products.aspose.org page |
| register-human-content | S-66 | Onboard a human-authored page into quality systems |
| repo-patrol | S-93 | Discover new FOSS repos across GitHub orgs |
| repo-scout | S-34 | Extract truth from FOSS repository |
| rubric-align | S-17 | Align content to quality rubric |
| section-enhance | S-96 | Inventory and propose improvements for a content section |
| seo-review | S-116 | Independent-agent review gate for pending SEO frontmatter recommendations (title/description/keywords), unblocking apply.py |
| session-start | S-77 | Mandatory session initialization gate |
| site-plan | S-47 | Production-grade pre-generation site manifest |
| stale-detect | S-13 | Identify stale content pages |
| system-heal | S-87 | Audit-driven content healing |
| ht-translate | S-HT-01 | Single-page translation via hugo-translator (explicit --site profile required) |
| ht-translate-batch | S-HT-02 | Batch translation via hugo-translator (explicit --site profile required) |
| triage-confirm | S-92 | Layer 2 body-prose staleness scanner |
| truth-audit | S-38 | Member-level API verification |
| truth-audit-content | S-85 | Line-level content truth audit |
| truth-index | S-31 | Generate knowledge index |
| truth-merge | S-35 | Promote scout + enriched claims into merged/ |
| update-registry | S-68 | Scan GitHub orgs and write data/products.json |

---

## Non-skill internal tooling

The following components are **not** skills and are deliberately excluded from the table
above (and from the S-12/S-91 skill-first execution mandate) — they must not be invoked
as `/command` entries or treated as satisfying "use the applicable skill" guidance.

| Component | Files | Status |
|-----------|-------|--------|
| ACT (Autonomous Content Tooling) | `scripts/pipeline/commands/content/shadow_content_generator.py`, `scripts/pipeline/lib/controlled_draft_writer.py` | Experimental, pilot-scoped (`pdf/go` only). Produces `draft: true` candidates only; never authoritative content. See `docs/reference/hugo-rendering.md` §4a for the full contract, including the promotion-gate requirement before any ACT-originated page may reach `draft: false`. |

Skill-based generation (the table above) is the default, authoritative content path.
ACT does not supersede or replace any skill listed above.

---

## Plan execution gate

Before executing any inherited, stale, or archive-containing plan, invoke
`plan-normalize` (S-91) to classify each section and determine execution safety.

If S-91 returns `execution-ready-as-is: no`, do not proceed. Amend the plan
first using S-91 in `amend` mode, then re-run assessment.

For mission-scale work (spanning multiple sessions or agents, not just a single inherited plan
file), see `AGENTS.md` §17 and `docs/governance/planning-methodology.md` — the planning-review
and taskcard-readiness checklists to apply before treating a newly-authored plan as executable.

See `docs/reference/skill-quality-gates.md` for the full gate inventory.
