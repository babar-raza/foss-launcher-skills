<!-- Source: AGENTS.md §12 Skills Reference
     Plan: delightful-wondering-hartmanis
     Extracted: 2026-04-29 -->

# §12 Skills Reference

> Deepens: AGENTS.md §12 (stub in root)

### Skills reference

| Skill | ID | Purpose |
|-------|----|---------|
| path-guard | S-01 | Enforce allowed write paths |
| project-phase-store | S-10 | Track generation phase state for a product (reads/writes reports/phase_state.json) |
| knowledge-diff | S-12 | Detect upstream repo changes |
| stale-detect | S-13 | Identify stale content pages |
| knowledge-update | S-14 | Refresh knowledge model from source |
| embed-knowledge | S-15 | Embed knowledge artifacts into dual vector stores (three-tier: professionalize.com → Ollama → TF-IDF) |
| rubric-align | S-17 | Align content to quality rubric |
| page-plan | S-18 | Plan page structure |
| page-draft | S-19 | Draft initial page content |
| page-update | S-20 | Update page after knowledge change |
| page-enhance | S-21 | Enhance page to meet quality bar |
| faq-generate | S-22 | Generate FAQ section |
| content-check | S-23 | Pre-write structural and quality check gate |
| evidence-cite | S-24 | Attach knowledge citations to content pages |
| eval-page | S-25 | Evaluate page grade |
| heal-page | S-26 | Heal low-quality page |
| truth-index | S-31 | Generate knowledge index |
| content-audit | S-32 | Semantic knowledge verification |
| change-guard | S-33 | Pre-write knowledge gate |
| repo-scout | S-34 | Extract truth from FOSS repository |
| truth-merge | S-35 | Promote scout + enriched claims into merged/ |
| cross-platform | S-36 | Family consistency check |
| knowledge-enrich | S-37 | LLM-enriched claims from scout api_surface (bounded-description mode). enrich.py returns False on total LLM failure (all providers unreachable) — do not proceed to S-35. `--no-llm` is the only path that writes empty `enriched_claims.json` and returns True. |
| truth-audit | S-38 | Member-level API verification (deep) |
| batch-remediate | S-40 | Full eval→fix→LLM→re-eval pipeline for all content pages of a product |
| batch-eval-fix | S-41 | Lightweight eval + deterministic auto-fixes only; no LLM pass; safe for unattended runs |
| category-fix | S-42 | Run a specific fixer on files by category code (ST, RV, EG, RL, AA, PC, FC, PT, CP, CG) |
| gap-eval | S-43 | Content verification against clone cache — publishability verdict. `Tier3Result` dataclass replaces `_TIER3_UNAVAILABLE` sentinel; three failure modes now distinguishable: `NOT_CONFIGURED`, `INTENTIONAL_SKIP` (no source context — data problem, not LLM), `UNREACHABLE`/`AUTH_FAILED`. Finding JSON includes `endpoint_status` and `endpoint_used` fields. |
| gap-plan | S-44 | Wave-ordered remediation planning from gap-eval findings |
| gap-report | S-45 | Cross-product gap synthesis report |
| gap-apply | S-46 | Execute wave-ordered fix specs from gap-plan output (Wave 1 auto-fix, Wave 2 LLM-planned substitutions, Wave 3 page generation, Wave 4 human escalation) |
| site-plan | S-47 | Production-grade pre-generation site manifest (deterministic YAML output) |
| family-sync | S-48 | Update family-level products page to reflect all launched platforms |
| launch-product | S-49 | 5-subdomain full documentation launch orchestrator (10 stages) |
| content-eval | S-51 | Multi-dimensional content evaluation (16 evaluators, grading, batch mode) |
| translate-page | S-52 | Translate a single English content page to target locales |
| translate-batch | S-53 | Batch translate all pages for a family/platform to target locales |
| knowledge-bootstrap | S-54 | Pre-condition gate; detects and resolves stale knowledge before content or validation commands |
| no-downgrade-guard | S-55 | Pre-write quality comparison to prevent content regression *(internal sub-routine — called by generation skills before write; not invoked directly by users)* |
| new-docs-page | S-56 | Generate documentation pages for docs.aspose.org |
| new-blog-post | S-57 | Generate blog posts for blog.aspose.org |
| new-kb-howto | S-58 | Generate KB how-to articles |
| new-kb-faq | S-59 | Generate or update FAQ page for a product platform |
| new-reference-page | S-60 | Generate API reference pages for reference.aspose.org |
| new-products-page | S-61 | Generate products.aspose.org landing pages |
| batch-reference | S-62 | Bulk reference page generation for all missing classes/enums; idempotent |
| code-smoke | S-63 | Syntax and type-check code blocks in content files (Python via py_compile/mypy; Java, C#, TypeScript, C++ via tree-sitter) |
| getting-started | S-64 | Fresh-clone onboarding: install deps, configure env, bootstrap knowledge, verify |
| link-validate | S-65 | Validate cross-subdomain internal links in content files; report BROKEN links where the target slug does not exist locally |
| register-human-content | S-66 | Onboard a human-authored page into quality and provenance systems (sets auto_updatable: false, attaches evidence, assigns grade baseline) |
| diagnose-skill-failure | S-67 | Governed diagnostic procedure when a skill or pipeline script fails; classifies failure as CONFIG/DATA/CODE/GOVERNANCE and produces a breakage report |
| update-registry | S-68 | Scan all 26 aspose-{family}-foss GitHub orgs, discover FOSS repos, and write data/products.json (supports --dry-run, --local-only, --force) |
| new-kb-index | S-69 | Scaffold KB platform section landing page |
| new-docs-index | S-70 | Scaffold Docs platform section landing page |
| new-reference-index | S-71 | Scaffold Reference platform section landing page |
| evidence-repair | S-72 | Repair evidence frontmatter for validator-blocked pages (P-03 or audit FAIL); evidence-frontmatter-only; never modifies body content; fail-closed; supports --dry-run |
| manual-edit | S-73 | Operator-directed targeted content edit: applies a human-specified targeted change (frontmatter, wording, code block, section rewrite) to a single file under full path-guard, evidence, provenance, and audit trail governance; revert-on-failure; single file per invocation |
| causal-backtrack | S-74 | Resolve upstream dependency failures: given evaluation findings with cause_class UPSTREAM_MISSING or BAD_LINK_FORMAT, classifies dependency root cause, invokes S-62/S-60 for missing targets or S-73 for wrong-URL fixes, and writes cause-classification.json + dependency-verification.json evidence; supports --dry-run |
| locale-patch | S-75 | Propagate targeted text fixes to locale translation copies of a fixed English source file; dry-run first; applies (old_text, new_text) patches to all locale variants; emits patch_report.md; never re-translates whole page |
| commit | S-76 | Full commit-prep workflow: inspect working tree, categorize changes, plan 2–8 Conventional Commits, handle override tokens for protected paths, add invoked-skill IDs to content commits, stage precisely (never git add -A), verify quality gates (pytest), create commits with structured bodies, clean up post-commit token lifecycle, print final summary |
| session-start | S-77 | Mandatory session initialization gate: read AGENTS.md + CLAUDE.md in full, confirm §2 Read Order and §6b capability assessment method, output SESSION GATE PASSED block before accepting any task |
| evidence-enhance | S-78 | Improve section evidence coverage on pages that already pass validation (audit.py PASS, grade A/B); thin wrapper around attach_evidence.py --force; evidence-frontmatter-only; never modifies body content; pre-flight audit required; revert-on-failure; use S-72 for validator-blocked pages |
| launch-rollback | S-79 | Revert one product's generated content files to last committed git state without touching system files (scripts/, .agents/, reports/, knowledge/); reads site_plan.yaml for file list; dry-run manifest first; backs `scripts/pipeline/commands/launch/launch_rollback.py` |
| coverage-reconcile | S-80 | Trace every knowledge unit (claim, API member) to a page disposition (used_in_content / excluded_by_planner / orphaned); writes `reports/coverage/{family}/{platform}/{date}-coverage-report.md`; backs `scripts/pipeline/commands/knowledge/knowledge_coverage.py` |
| knowledge-coverage-audit | S-81 | Per-claim disposition table: maps every claim in merged/claims.json to exactly one disposition (USED_EVIDENCE / SURFACE_ONLY / EXCLUDED_THRESHOLD / EXCLUDED_TIER / ORPHANED); writes `reports/coverage/{family}/{platform}/knowledge_coverage.json` and `.md`; backs `scripts/pipeline/commands/knowledge/knowledge_coverage.py` |
| delta-site-plan | S-82 | Incremental site planning after knowledge update: runs `site_planner.py --mode update` to compute pages_to_add, pages_to_update, pages_to_remove, pages_renamed; writes delta section to site_plan.yaml; requires knowledge_delta.json from S-14 |
| page-retire | S-83 | Retire obsolete content pages via `draft: true` + `retired_at` frontmatter (Hugo standard); never deletes files; dual-signal retirement rule (cluster + claim signal); --dry-run first; backs `scripts/pipeline/commands/healing/retire_page.py` |
| refresh-product | S-84 | Full post-launch product refresh orchestration: 16-step chain from S-12 (detect) through S-14, S-82, **Step 3.5 PIA** (page_impact_assess.py), S-20, delta-dispatch, S-83, S-62 --update, S-48, S-23, S-65, S-53, **Step 13.5 coverage-report** (refresh_review.py), verification gate (post_refresh_verify --verify including Check 6 coverage completeness), and S-76 (commit); early-exit if no SHA change; post-conditions: `reports/refresh_review/{family}/{platform}/page_decisions.json` covers all 5 subdomains + `coverage_report.md` shows all subdomains assessed |
| truth-audit-content | S-85 | Line-level content truth audit against clone cache and knowledge model (read-only; decomposes pages into units, verifies each, produces gap ledger); backs `scripts/pipeline/commands/diagnostics/truth_audit_content.py` |
| refresh-product-page | S-86 | Re-generate a single products.aspose.org landing page through the full S-61 pipeline with no-downgrade-guard protection; use when S-61 template has been improved and existing pages should benefit |
| system-heal | S-87 | Audit-driven content healing: deterministic baseline (--no-llm) → extended baseline (LLM + tier3_cache) → origin classification (origin_map.py) → content healing (S-74/S-46/S-26 by route) → pipeline evidence report → re-verify → commit or escalate; 8-phase; max 50 findings (use S-44+S-46 above that); AMBIGUOUS and tier3_non_determinism_flag findings never auto-repaired; backs `scripts/gap-eval/src/origin_map.py` + `scripts/gap-eval/src/tier3_cache.py` |
| backlog | S-88 | Unified backlog management and planning: view briefing, automated plan scanning (with `.claude/plans/` repo-affinity filtering), add items (with intake dedup), investigate (intake), investigate-run (execute existing INV item inline — reads brief, gathers evidence, records findings, moves to Resolved), surface (contextual item surfacing — scores backlog against response context, returns top matches; called automatically by session-start), remind, session handoff, archive, triage inbox, reconcile (with cross-item analysis), status investigation, plan creation, replan amendment, plan hardening, traceability, governed closeout, merge, group, link, **harvest** (automatic report → backlog intake: extracts open items from qualifying reports via `report_extract.py`, routes through harvest ledger for dedup/state tracking via `harvest_ledger.py`, auto-intakes high-confidence items to inbox, queues low-confidence for review; primary trigger: report finalization by S-87/S-76; secondary: `/backlog update` step 1b; safety net: `/session-start` step 6 advisory + `/backlog reconcile` step 8d); all state in `backlog/` + `plans/from_backlog/` (gitignored); 23 subcommands |
| heal-batch | S-89 | Batch healing from content_eval report: routes findings through heal policy table to auto/llm/regen modes in a single pass; auto-mode applies deterministic fixers; llm-mode emits S-26 invocation descriptors; regen-mode emits causal-backtrack descriptors with `regen_after` flags; optional before/after verification with regression detection; supersedes deterministic portion of S-40 (batch-remediate); backs `scripts/pipeline/commands/content/remediate.py heal` |
| publish-readiness-review | S-90 | Agent-executed governed inspection — replaces all "human-review" dead-ends with bounded inspection, judgment, skill routing, re-verification, and verdict; reads audit context, classifies pages (PUBLISH-READY / NEEDS-ACTION / ACCEPTABLE-GRADE-C / STRUCTURAL-GAP / BLOCKED), routes to S-21/S-26/batch-reference/S-65/S-38/S-73/S-74; H-gate equivalents for H-01..H-05; writes inspection-manifest.json + action-log.json + final-verdict.md; supports --scope, --triage-unknowns, --dry-run; backs `skills/publish-readiness-review.md` |
| plan-normalize | S-91 | Execution-safe plan quality gate — classifies every section of a plan (historical-reference / verified-current-state / completed-archive / open-actionable / operator-guidance / design-rationale / intentionally-omitted), verifies claims against current repo state, extracts only still-open work, marks each item ready/blocked/stale/already-done/needs-replan, selects single next executable item, blocks execution on ambiguous sections or unverified capabilities; modes: assess (verdict only), amend (writes exec-pack sibling or edits in-place), launch (assess + amend + execute first safe item); mandatory gate before executing inherited, long, amended, or archive-containing plans; backs `skills/plan-normalize.md` |
| triage-confirm | S-92 | Layer 2 body-prose staleness scanner for the refresh pipeline — complements Layer 1 SHA-based detection (refresh_knowledge.py) by scanning page body prose for references to API classes or knowledge claims that have changed or been removed; returns stale/current verdict with per-finding reasons; invoked by S-84 (refresh-product) Step 9.5 and S-89 (heal-batch) triage phase; backs `scripts/pipeline/lib/triage_confirm.py` + `scripts/pipeline/lib/reconcile_triage.py`; skill file: `skills/triage_confirm.md` |
| repo-patrol | S-93 | Discover new FOSS repos across 26 GitHub orgs, score confidence, and produce `reports/discovery/patrol_report.json`; default dry-run (no registry changes); `--apply` adds candidates to `data/products.json` with `status: candidate`; `--inactive-days` threshold (default 180); `--force` re-evaluates rejected repos; backs `scripts/pipeline/commands/diagnostics/repo_patrol.py scan`; skill file: `skills/repo-patrol.md` |
| change-sweep | S-94 | Batch SHA comparison across all active launched products in `data/products.json`; reads `knowledge/{family}/{platform}/merged/model.yaml` stored SHA, updates clones, classifies impact HIGH/MEDIUM/LOW; produces `reports/discovery/sweep_report.json`; read-only (does NOT set `stale_since` — S-12's job); backs `scripts/pipeline/commands/diagnostics/repo_patrol.py sweep`; skill file: `skills/change-sweep.md` |
| discovery-triage | S-95 | Route patrol and sweep reports to backlog actions — reads `reports/discovery/patrol_report.json` + `sweep_report.json`, creates backlog items per §9 decision trees; **MVP: NEVER directly invokes S-12 or S-84** — all findings route to backlog items only; direct auto-refresh gated behind TC-GATE-01 post-pilot; backs `skills/discovery-triage.md` |
| section-enhance | S-96 | Inventory a target content section across any subdomain, detect gaps against clone-cache and knowledge truth, and generate a read-only proposal pack; Phase 1 is proposal-only (zero writes to `content/`); accepts any plausible target input form, resolves to canonical repo path recording all alias corrections; backs `skills/section-enhance.md` |
| content-enrich | S-98 | Post-launch cross-subdomain content enrichment audit, candidate generation, and governed execution; three modes (audit, plan/dry-run, execute); builds coverage matrix across products/docs/kb/blog/reference, classifies candidates with denominator invariant, defers/rejects weak candidates to backlog; blog quality gate; conservative execute via handoff manifest to S-56/S-57/S-58/S-20; backs `scripts/pipeline/commands/enrichment/content_enrich.py`; lib: `scripts/pipeline/lib/enrichment/` |
| cleanroom-regen | S-97 | Full cleanroom regeneration workflow for one `{family}/{platform}` target: regenerate from scratch, diff vs baseline, apply page-type-aware editorial verdicts, selective revert bad files, verify, and produce commit-readiness gate; 8 modes (inspect, snapshot, regenerate-cleanroom, diff, review, apply-decision, verify, commit-ready); two-phase agent dispatch for non-reference subdomains; backs `scripts/pipeline/commands/ops/cleanroom_regen.py`; skill file: `skills/cleanroom-regen.md` |
| pipeline-harden | S-99 | Parameterized pipeline hardening sprint: investigation (claim audit, hidden problem discovery, gap taxonomy), phased execution (fixtures, code fixes, manifests, healing, gates, docs), evidence bundle; no content/ writes; checkpoint-based resume; reuses evidence/, skill_context.py, project_phase_store.py, healing data models, triage_confirm; skill file: `skills/pipeline-harden.md` |

**S-43 (gap-eval) CLI flags:**
- `--deterministic` — Exhaustive Stage 2 + no LLM (Tier 1 + Tier 2 only). Fully reproducible. Recommended for regression tracking and CI integration.
- `--seed N` — Random seed for Stage 2 sampling (default: 42). Only used when `--max-stage2-entries > 0`.
- `--max-stage2-entries N` — Stage 2 entries to check: 0 = all entries (default, exhaustive); N > 0 = sample N entries.
- `--no-tier3-cache` — Bypass Tier 3 result cache; force fresh LLM calls for all Tier 3 findings;
  write results back to cache after evaluation. Use when suspecting cache staleness or testing
  Tier 3 behavior. **Performance ceiling:** for products with > 50 content files, a full
  `--no-tier3-cache` run requires one LLM call per Tier 3 finding and typically exceeds 5 minutes
  (may time out in CI with default 2-min limits). Use `--deterministic` for CI and reserve
  `--no-tier3-cache` for targeted local diagnosis. (Added with S-87/tier3_cache.py.)

### Enforcement scripts

| Script | Purpose |
|--------|---------|
| `scripts/pipeline/commands/content/audit.py` | Deterministic S-23 content-check: verifies every API token in content against `api_surface.json` |
| `scripts/pre-commit-audit.sh` | Pre-commit hook — blocks commits with API accuracy FAILs |
| `.github/workflows/content-audit.yml` | CI — blocks PRs with API accuracy FAILs |
| `scripts/pipeline/content_eval/` | Multi-dimensional content evaluation (16 evaluators); run via `python scripts/pipeline/commands/content/run_content_eval.py evaluate {family} {platform}` (no PYTHONPATH needed) or `python -m content_eval ...` from `scripts/pipeline/`. DEFAULT_EVALUATORS = 9 (fast/deterministic); ALL_EVALUATORS = 16. |
| `scripts/pipeline/commands/content/run_content_eval.py` | Wrapper entrypoint for content_eval — invoke from repo root without any PYTHONPATH prefix. Use this instead of `PYTHONPATH=scripts/pipeline python -m content_eval`. |
| `scripts/pipeline/commands/content/batch_reference.py` | Backing script for S-62 (batch-reference) — generates template-based reference pages from api_surface.json for headless/CI runs. CLI: `python scripts/pipeline/commands/content/batch_reference.py {family} {platform} [--kind class\|enum\|all] [--limit N] [--dry-run]`. |
| `scripts/pipeline/commands/knowledge/refresh_knowledge.py` | Runs the full knowledge pipeline (scout→enrich→promote→index), auto-clears `stale_since` in `merged/model.yaml` after successful refresh, and writes `merged/knowledge_delta.json` with semantic diff. CLI: `python scripts/pipeline/commands/knowledge/refresh_knowledge.py {family} {platform} [--no-auto-fetch] [--check-only]`. |
| `scripts/pipeline/commands/healing/retire_page.py` | Retire content pages via `draft: true` + `retired_at` frontmatter (Hugo standard); backs S-83 (page-retire). CLI: `python scripts/pipeline/commands/healing/retire_page.py {file-path} [--dry-run]` or `--from-plan {site_plan_path}`. |
| `scripts/pipeline/commands/ops/post_refresh_verify.py` | Post-refresh verification gate and progress tracker; backs S-84 (refresh-product). CLI: `python scripts/pipeline/commands/ops/post_refresh_verify.py {family} {platform} --step {name}` / `--verify` / `--status`. |
| `scripts/ci/checks/check_skill_readme_coverage.py` | Documentation coverage: asserts README.md exists in all four skill trees (skills/, .claude/commands/, .agents/skills/, .kilocode/skills/) and root README.md links to skills. **Blocking** (no continue-on-error). |

Usage:
```
python scripts/pipeline/commands/content/audit.py slides python       # Single product
python scripts/pipeline/commands/content/audit.py all                  # All products
python scripts/pipeline/commands/content/audit.py --files path1.md     # Specific files (pre-commit)
python scripts/pipeline/commands/content/audit.py all --json           # Machine-readable output
```


### Skill locations (per agent)

| Agent | Skills path | Instructions file |
|-------|------------|-------------------|
| Claude Code | \ | \ |
| Codex CLI | \ | \ + \ |
| Kilo Code | \ | \ |
| Canonical source | \ | — |

Each tree has a \ at its root describing its contents, invocation syntax, and any divergence from canonical. See [\](skills/README.md) for the primary catalog.

#### Internal skills (auto-invoked sub-routines)

The following 8 skills exist in canonical \ and in \ and \ trees, but are **intentionally absent from \**. They are auto-invoked by other skills and are never called directly by users or agents.

| Slug | ID | Role |
|------|----|------|
| \ | S-54 | Pre-condition gate before content or validation commands |
| \ | S-24 | Attaches knowledge citations; auto-invoked by generation skills |
| \ | S-01 | Enforces allowed write paths; auto-invoked on every write |
| \ | S-33 | Pre-write knowledge gate; auto-invoked before content writes |
| \ | S-55 | Pre-write quality comparison sub-routine |
| \ | S-17 | Sub-evaluator called by eval-page |
| \ | S-44 | Planning sub-tool for the remediation pipeline |
| \ | S-10 | Checkpoint infrastructure |

Source: \.

#### Claude Code-only extras (not registered skills)

The following files exist **only in \**. They are not registered in the skills reference table, have no file in canonical \, and are not present in \ or \ trees.

| File | Role |
|------|------|
| \ | Dispatcher: routes to \ (S-52) or \ (S-53) based on argument type. Convenience wrapper; adds no new capability. |
| \ | Interactive human review gate for SEO recommendations. Claude Code utility; not yet a registered skill. |

Source: \.
