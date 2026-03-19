# Responsibility Map — foss-launcher-skills

> Date: 2026-03-19
> Classification: Where each module belongs in the target architecture

---

## Classification Legend

| Label | Meaning |
|-------|---------|
| **PRODUCT CORE** | Product-facing, must remain in foss-launcher-skills |
| **NEW IP** | Genuinely new logic not present in launcher |
| **BOUNDARY LAYER** | Thin glue between launcher output and product pipeline |
| **IMPORT** | Should be consumed from launcher, not owned locally |
| **KEEP TEMP** | Keep temporarily, re-evaluate when launcher provides equivalent |
| **RUNTIME DATA** | Generated state, must not be in source tree |
| **REFACTOR** | Stays here but needs redesign |

---

## Module Classification Table

| Module | Lines | Current Responsibility | Classification | Stay Here? | Reasoning |
|--------|-------|----------------------|---------------|------------|-----------|
| `skills/` (36 .md) | ~4,000 | Canonical agent skill definitions | **PRODUCT CORE** | YES | This IS the product. Single source of truth for all agent platforms. Every agent-specific output derives from these. |
| `tools/distribute.py` | ~200 | Generate agent-specific skill layouts (.claude/, .agents/, .kilocode/) | **PRODUCT CORE** | YES | Distribution logic is product-specific. Must be enhanced with manifest generation, DAG validation, capability filtering. |
| `AGENTS.md` | 179 | Governance: roles, autonomy tiers, hard stops, skill chains | **PRODUCT CORE** | YES | Governance model is the product's operational contract. Human-maintained, agent-readable. |
| `config.yaml` | 102 | Site paths, forbidden paths, golden corpus settings, governance | **PRODUCT CORE** | YES (refactor) | Product configuration. Needs schema validation, removal of absolute paths, addition of `data_root`. |
| `configs/families.yaml` | — | Product family × platform taxonomy (21 × 13) | **PRODUCT CORE** | YES | Product-specific taxonomy. Not duplicated from launcher. |
| `configs/intake_config.yaml` | — | 24 GitHub orgs for product discovery | **PRODUCT CORE** | YES | Input config for discover pipeline. Product-specific scope. |
| `configs/schemas/` (5 files) | — | JSON schemas for PEF, mental_model, verification, decision, diff | **PRODUCT CORE (NEW IP)** | YES | Evidence contract definitions. Unique to this product. |
| `scripts/materialize.py` | 274 | Build PEF from merged knowledge artifacts | **NEW IP** | YES | Does not exist in launcher. Core evidence pipeline. Aggregates knowledge into canonical evidence snapshot. |
| `scripts/mental_model.py` | 294 | Derive capability tiers, gap analysis, readiness | **NEW IP** | YES | Does not exist in launcher. Transforms PEF into actionable product assessment. |
| `scripts/decide.py` | 310 | Determine per-page content actions from evidence state | **NEW IP** | YES | Does not exist in launcher. Decision engine: create/update/enhance/verify_only/no_change. |
| `scripts/verify.py` | 341 | Deterministic content verification against PEF | **NEW IP** | YES | Does not exist in launcher. Grounds content to evidence with citation extraction and forbidden-claim detection. |
| `scripts/differ.py` | 296 | Compare PEF snapshots to surface evidence drift | **NEW IP** | YES | Does not exist in launcher. Change detection: claims added/removed/modified, API surface changes, format changes. |
| `scripts/merge.py` | 510 | Consolidate scout + external knowledge with provenance | **BOUNDARY LAYER** | YES | Thin enough (510 lines). Consumes scout output, produces evidence pipeline input. Glue, not duplication. |
| `scripts/index.py` | 197 | Generate per-product knowledge index | **BOUNDARY LAYER** | YES | Thin (197 lines). Derives metadata from merged artifacts. Local computation, not shared logic. |
| `scripts/config_loader.py` | — | Config resolution: load YAML, resolve paths, template substitution | **REFACTOR** | YES | Product-specific. Needs caching, schema validation, `data_root` support. |
| `scripts/schema_validate.py` | 86 | JSON schema validation helper | **PRODUCT CORE** | YES | Small, stable utility. Used by evidence pipeline for artifact validation. |
| `scripts/readme_sync.py` | 191 | README freshness detection and update | **PRODUCT CORE** | YES | Product-specific maintenance tool. Tracks skill count, script list, directory structure. |
| `scripts/scout.py` | 1,755 | Tree-sitter extraction across 6 languages | **IMPORT** | NO — move to launcher | Duplicates launcher intake. 1,755 lines of grammar-specific extraction that must track tree-sitter updates across Python, C#, Java, C++, TypeScript, JavaScript. Highest maintenance burden in the repo. |
| `scripts/discover.py` | 574 | GitHub org scanning with rate limiting and state persistence | **IMPORT** | NO — move to launcher | Explicitly "Adapted from foss-launcher/src/launcher/intake/org_scanner.py". Identical purpose. 574 lines of API integration code that belongs in launcher. |
| `scripts/golden_index.py` | 410 | Parse golden corpus into indexed JSON | **IMPORT** | NO — move to launcher | "Ported from foss-launcher's golden_loader.py". Golden corpus is launcher's asset; indexing should be launcher's responsibility. |
| `scripts/golden_conformance.py` | 438 | Score structural alignment with golden templates | **IMPORT** | NO — move to launcher | "Ported from foss-launcher's evaluate/checks/golden_conformance.py". Evaluation logic belongs in launcher's evaluate subsystem. |
| `scripts/refresh_golden.py` | 133 | Sync golden corpus from launcher filesystem | **KEEP (simplify)** | YES | Thin sync utility (133 lines). Simple file copy with change tracking. Keep as optional maintenance tool, but simplify to remove launcher filesystem assumptions. |
| `scripts/corpus_scan.py` | 388 | Profile existing content and build golden corpus references | **KEEP TEMP** | YES (for now) | Somewhat unique to this product's golden anchoring pattern. Low launcher overlap. Re-evaluate when launcher adds content profiling. |
| `scripts/embed.py` | 447 | Dual-tier embedding with API and local fallback | **KEEP TEMP** | YES (for now) | Independent embedding logic. Not clearly duplicated in launcher. Re-evaluate when launcher adds vector store support. |
| `golden/` | — | Curated exemplar content files | **RUNTIME DATA** | NO — move to `$data_root` | Synced asset, not source code. Refreshed from launcher via refresh_golden.py. Should not be version-controlled in product repo. |
| `knowledge/` | — | Extracted and merged knowledge artifacts | **RUNTIME DATA** | NO — move to `$data_root` | Generated by pipeline (scout → merge → index). Runtime state. |
| `evidence/` | — | PEF, mental models, verification reports, decisions, diffs | **RUNTIME DATA** | NO — move to `$data_root` | Generated by evidence pipeline. Runtime state. |
| `output/` | — | Generated content pages, install tests | **RUNTIME DATA** | NO — move to `$data_root` | Generated output. Runtime state. |
| `reports/` | — | Audit logs, conformance reports, launch reports | **RUNTIME DATA** | NO — move to `$data_root` | Generated output. Runtime state. (Exception: this audit report is a one-time source artifact.) |
| `plans/` | — | Page plans and healing workflows | **RUNTIME DATA** | NO — move to `$data_root` | Generated by skill execution. Runtime state. |
| `tests/` (18 files) | — | Unit and integration tests | **REFACTOR** | YES | Needs shared conftest.py, config fixtures, proper package imports. Remove sys.path.insert hacks. |

---

## Summary by Classification

| Classification | Module Count | Lines | Action |
|---------------|-------------|-------|--------|
| PRODUCT CORE | 10 modules | ~4,900+ | Keep and maintain |
| NEW IP | 5 scripts + schemas | ~1,515 | Keep — this is the differentiator |
| BOUNDARY LAYER | 2 scripts | ~707 | Keep as thin glue |
| IMPORT from launcher | 4 scripts | 3,175 | Replace with adapter calls |
| KEEP TEMP | 2 scripts | ~835 | Keep for now, re-evaluate |
| KEEP (simplify) | 1 script | ~133 | Simplify, keep as utility |
| REFACTOR | 2 modules | — | Redesign (config, tests) |
| RUNTIME DATA | 6 directories | — | Move out of source tree |

---

## Key Takeaway

The product's legitimate local IP is ~2,200 lines of evidence pipeline + ~700 lines of boundary-layer glue + skills + governance + schemas + distribution. The remaining ~5,000 lines of pipeline code should be consumed from launcher through a defined adapter boundary — not maintained as local copies.
