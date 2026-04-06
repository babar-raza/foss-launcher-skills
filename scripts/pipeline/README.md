# Pipeline — Knowledge Extraction & Content Validation

## Purpose

This pipeline extracts the API surface, format support, code snippets, and structured claims from FOSS source repositories using tree-sitter AST parsing, enriches them with LLM-generated semantic claims grounded in the verified API surface, promotes the combined knowledge into a unified model, validates published content pages against that model for factual accuracy, and supports evidence-based content generation. It is the source of truth for everything the Aspose FOSS documentation sites can claim.

## Quick Start (Fresh Clone)

```bash
# 1. Install Python dependencies (from repo root)
pip install -r scripts/requirements.txt

# 2. Set environment variables
cp .env.example .env          # then fill in GITHUB_TOKEN, PROFESSIONALIZE_API_KEY

# 3. Populate the product registry from GitHub
python scripts/pipeline/update_product_registry.py --token $GITHUB_TOKEN

# 4. Clone product repos (auto-clone from products.json)
python scripts/pipeline/refresh_knowledge.py --all --check

# 5. Bootstrap knowledge for a product
python scripts/pipeline/scout.py 3d python runs/.clone_cache/aspose_3d_python knowledge/3d/python/scout
python scripts/pipeline/enrich.py 3d python
python scripts/pipeline/promote.py 3d python
python scripts/pipeline/index.py 3d python

# 6. Optionally embed into vector stores
python scripts/pipeline/embed.py 3d python

# 7. Verify content against knowledge
python scripts/pipeline/audit.py 3d python
```

## Architecture

```
FOSS repo (git clone)
    |
    v
scout.py  ──────────────────────────────> knowledge/{family}/{platform}/scout/
    (tree-sitter AST extraction)              api_surface.json, claims.json,
    (detection: formats, limitations,         formats.json, snippets/, model.yaml
     snippets, identity claims)
    |
    v
enrich.py  ─────────────────────────────> knowledge/{family}/{platform}/scout/enriched_claims.json
    (LLM bounded-description enrichment)     ERC-prefixed claims grounded in api_surface.json
    (gpt-oss → ollama fallback)              claim_source: "llm_enriched"
    |
    v
promote.py  ────────────────────────────> knowledge/{family}/{platform}/merged/
    (scout-only promotion: no FL)             claims.json (provenance: scout|enriched|supplemental)
    (appends enriched_claims if present)      api_surface.json, api_surface.md
    (guard: exits 1 if fl/ exists)            formats.md, model.yaml, merge_report.md
    |
    v
index.py  ──────────────────────────────> knowledge/{family}/{platform}/merged/index.json
    (build knowledge index)                   class list, format tables,
    (snippet coverage metrics)                api_coverage stats

    |
    v
embed.py  ──────────────────────────────> knowledge/_vectors/{tier}/
    (vector store generation)                 claims.vectors.json, api.vectors.json

    |
    v
Content validation pipeline
    audit.py          — API token verification vs. api_surface.json
    content_audit.py  — Semantic prose tier classification
    content_eval/     — 16-evaluator multi-dimensional evaluation
    change_guard.py   — Pre-write forbidden-claim gate
    attach_evidence.py — Evidence frontmatter generation
```

## Entry Points (CLI)

All commands must be run from the **repo root** (the directory that contains `knowledge/`).

| Script | Purpose | CLI Usage | Produces |
|--------|---------|-----------|---------|
| `scout.py` | AST extraction from FOSS repo | `python scripts/pipeline/scout.py {family} {platform} {repo_path} {output_dir}` | `scout/` artifacts |
| `enrich.py` | LLM enrichment from scout artifacts | `python scripts/pipeline/enrich.py {family} {platform}` | `scout/enriched_claims.json` |
| `promote.py` | Scout-only knowledge promotion | `python scripts/pipeline/promote.py {family} {platform}` | `merged/` artifacts |
| `index.py` | Knowledge index generator | `python scripts/pipeline/index.py {family} {platform}` or `all` | `merged/index.json` |
| `embed.py` | Vector store generation | `python scripts/pipeline/embed.py {family} {platform}` or `all` | `knowledge/_vectors/` |
| `audit.py` | API accuracy audit | `python scripts/pipeline/audit.py {family} {platform}` or `all` or `--files` | `reports/audit/` |
| `attach_evidence.py` | Evidence frontmatter generator | `python scripts/pipeline/attach_evidence.py {family} {platform}` or `all` or `--files` | Updated frontmatter |
| `content_audit.py` | Semantic prose audit | `python scripts/pipeline/content_audit.py {family} {platform}` or `all` | `reports/audit/` |
| `change_guard.py` | Pre-write knowledge gate | `python scripts/pipeline/change_guard.py {family} {platform} "text"` | exit 0/1/2 |
| `refresh_knowledge.py` | Auto-refresh stale knowledge | `python scripts/pipeline/refresh_knowledge.py {family} {platform}` or `--all` | Updated `merged/` |
| `update_product_registry.py` | Sync product registry from GitHub | `python scripts/pipeline/update_product_registry.py [--token TOKEN]` | `data/products.json` |
| `remediate.py` | Batch auto-fix eval findings | `python scripts/pipeline/remediate.py triage\|fix\|report\|status <report.json>` | `reports/remediation/` |

## Sub-packages

| Package | Purpose | Key modules |
|---------|---------|------------|
| `core/` | Shared infrastructure | `fs.py`, `manifest.py`, `clone_cache.py`, `constants.py` |
| `extraction/` | AST extraction engine | `scout.py`, `api_surface.py`, `tree_helpers.py`, `formats.py`, `snippets.py` |
| `audit/` | Content API verification | `runner.py`, `links.py`, `snippets.py`, `reports.py` |
| `evidence/` | Evidence frontmatter | `runner.py`, `mapper.py`, `sections.py`, `writer.py` |
| `content_eval/` | Multi-dimensional evaluation | `cli.py`, `config.py`, `evaluators/`, `remediation/` |
| `verification/` | Re-export namespace for token ops | `extractor.py`, `verifier.py` |
| `scout_enrichers/` | Docstring enrichment | `_doxygen.py`, `_javadoc.py`, `_xml_doc.py` |

## Knowledge Directory Structure

```
knowledge/
  {family}/
    {platform}/
      scout/              # Raw extraction output (scout.py)
        api_surface.json
        claims.json
        formats.json
        model.yaml
        snippets/
          snippets_index.json
          snippet_001.py  (etc.)
      merged/             # Promoted output (promote.py + index.py)
        api_surface.json
        api_surface.md    # Human-readable, used in LLM prompts
        claims.json       # With provenance: scout | enriched | supplemental
        formats.json
        formats.md
        index.json        # Built by index.py
        model.yaml        # Authoritative metadata; stale_since field
        merge_report.md
        snippets/
          snippets_index.json
      .pipeline_state.json  # Step completion tracking (core/manifest.py)
  _vectors/
    api/                  # API-tier vector store
    local/                # Local-tier vector store
    _index.json           # Aggregated product listing
```

## Configuration

| File | Purpose |
|------|---------|
| `scripts/requirements.txt` | Python dependencies: tree-sitter, pyyaml, requests |
| `data/products.json` | Product registry: family, platform, clone_url, active flag |
| `.env` | `GITHUB_TOKEN`, `PROFESSIONALIZE_API_KEY` |
| `runs/.clone_cache/` | FOSS repo shallow clones (git-ignored) |

## Common Workflows

### (a) Bootstrap a new product

```bash
python scripts/pipeline/update_product_registry.py --token $GITHUB_TOKEN
python scripts/pipeline/refresh_knowledge.py 3d python
python scripts/pipeline/index.py 3d python
python scripts/pipeline/audit.py 3d python
```

### (b) Refresh after upstream changes

```bash
python scripts/pipeline/refresh_knowledge.py 3d python
python scripts/pipeline/index.py 3d python
python scripts/pipeline/audit.py 3d python
```

### (c) Audit existing content

```bash
python scripts/pipeline/audit.py 3d python
python scripts/pipeline/content_audit.py 3d python
```

### (d) Run full content evaluation

```bash
cd scripts/pipeline
python -m content_eval evaluate 3d python
python scripts/pipeline/remediate.py triage reports/content_eval/eval-*.json
python scripts/pipeline/remediate.py fix reports/content_eval/eval-*.json
```

## Output Artifacts

| Artifact | Location | Description |
|----------|---------|-------------|
| `api_surface.json` | `knowledge/{f}/{p}/scout/` | Raw class/method/property list |
| `api_surface.md` | `knowledge/{f}/{p}/merged/` | Human-readable API surface for LLM injection |
| `claims.json` | `knowledge/{f}/{p}/merged/` | Merged claims with provenance tags |
| `formats.json` | `knowledge/{f}/{p}/merged/` | Supported file formats with import/export flags |
| `model.yaml` | `knowledge/{f}/{p}/merged/` | Authoritative metadata; `stale_since` field |
| `index.json` | `knowledge/{f}/{p}/merged/` | Navigable index with class list, format tables, coverage |
| `snippets_index.json` | `knowledge/{f}/{p}/merged/snippets/` | Code example index with `classes_used` |
| `quality_trend.jsonl` | `reports/audit/` | Per-run FAIL/WARN counts over time |
| `batch-audit-*.md` | `reports/audit/` | Human-readable audit report |
| `eval-*.md` / `eval-*.json` | `reports/content_eval/` | Content evaluation reports |
| `rem-*.md` / `rem-*.json` | `reports/remediation/` | Remediation triage and fix reports |

## Environment Variables

| Variable | Required | Purpose |
|----------|----------|---------|
| `GITHUB_TOKEN` | For `update_product_registry.py` | GitHub PAT to scan FOSS orgs |
| `PROFESSIONALIZE_API_KEY` | Optional | API-tier embedding endpoint; TF-IDF fallback if absent |
| `ASPOSE_CLONE_CACHE` | Optional | Override default `runs/.clone_cache/` clone location |
| `ASPOSE_ORG` | Optional | Comma-separated GitHub orgs to scan (default: 5 aspose-*-foss orgs) |

## Failure Modes

| Symptom | Likely cause | Fix |
|---------|-------------|-----|
| `ImportError: No module named 'tree_sitter'` | Missing tree-sitter | `pip install -r scripts/requirements.txt` |
| `ERROR: No scout knowledge found` | Missing `scout/claims.json` | Run `scout.py` first |
| `SKIP: no knowledge model` | Missing `merged/model.yaml` | Run `promote.py` then `index.py` |
| `stale_since != null` in model.yaml | Knowledge is outdated | Run `refresh_knowledge.py` |
| Evaluator exception in content_eval | Unexpected page structure | Check stderr; evaluator errors emit WARN findings |
| `No clone_url in products.json` | Registry not populated | Run `update_product_registry.py --token` |

## Script Inventory

All root `.py` scripts in `scripts/pipeline/` (currently **69 files**) are tracked in
`scripts/pipeline/registry.yaml`. A human-readable view is generated from the registry:

```bash
python scripts/ci/render_inventory.py     # validates + regenerates INVENTORY.md
python scripts/ci/render_inventory.py --check   # validate only
```

> **Do not edit `INVENTORY.md` directly.** Edit `registry.yaml` and regenerate.

When adding a new script, follow the New File Protocol in `PIPELINE.md`.

## Notes for Agents

- Always run pipeline scripts from the **repo root** (not from `scripts/pipeline/`)
- Never write content without running `audit.py` first (S-23 skill)
- `knowledge/` is the source of truth for all content; always read `model.yaml` before editing pages
- If `model.yaml` has `stale_since != null`, stop and run `refresh_knowledge.py` (skills S-12, S-14)
- Evidence frontmatter (`evidence:` block) is internal-only — never expose it to end users
