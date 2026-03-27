# SEO Pipeline

Automated keyword-gap analysis and safe frontmatter improvement for all aspose.org content sites.

---

## 1. Overview

The SEO pipeline ingests Google Search Console (GSC) performance data and LLM-derived topic signals, identifies pages whose frontmatter is underselling their content, generates evidence-grounded recommendations, and produces a patch manifest that a human operator can review and apply via a gated CI workflow.

**What the pipeline does:**
- Validates keyword assets (family keyword files, GSC export CSVs)
- Builds a full inventory of published content pages
- Maps GSC query/URL data to filesystem content files
- Scores keyword-gap opportunities per page
- Generates title, description, and tag recommendations grounded in knowledge files
- Applies a multi-layer safety check before producing any patch
- Emits per-page reports, a summary dashboard, a structured patch manifest, and a pipeline run log
- Applies approved patches via YAML surgery (frontmatter only)
- Verifies improvement via before/after opportunity snapshot comparison

**What the pipeline does NOT do:**
- No body text edits — prose, headings, and code examples are never touched
- No evidence block changes — `evidence:` frontmatter sections are read-only
- No knowledge model writes — `knowledge/` artifacts are inputs, never outputs
- No auto-merge — all patches require a human to trigger `seo-apply.yml` with `dry_run=false`

---

## 2. Two Data Tracks

The pipeline combines two complementary signals:

| Track | Source | What it provides |
|-------|--------|-----------------|
| **Track 1 — GSC real data** | `reports/gsc/` CSV exports from the `gsc-query-collector` workflow (runs Sundays) | Actual queries, impressions, clicks, and position data for pages already indexed by Google. High confidence, covers only existing traffic. |
| **Track 2 — LLM topic signals** | LITELLM_KEY → `llm.professionalize.com` | Generates candidate keyword sets for pages with no GSC history (new content, zero-traffic pages). Lower confidence; all LLM suggestions are gated through the safety filter before use. |

Both tracks feed into `analyze.py` and produce a unified opportunities list ranked by estimated impact.

**GSC subdomain coverage:** The `gsc-query-collector` workflow is authorized for all 7 subdomains:
`www`, `products`, `reference`, `websites`, `docs`, `blog`, `kb`. Phase 0a is complete — Track 1 data is available for all subdomains.

---

## 3. Module Summary

| Module | Purpose | Primary Input | Primary Output |
|--------|---------|---------------|----------------|
| `validate.py` | Confirm keyword assets and GSC data are present and well-formed | `keywords/*.json` | `reports/seo/validation_report.json` |
| `inventory.py` | Walk all content trees, extract frontmatter for every English index page | `content/` | `reports/seo/page_index.json` |
| `map_url.py` | Join GSC URL records to inventory entries by URL slug | `reports/seo/page_index.json`, `reports/gsc/` | Appends `url_map` key to `page_index.json` |
| `analyze.py` | Score keyword gaps; merge Track 1 and Track 2 signals | `page_index.json` (with url_map), `keywords/*.json` | `reports/seo/opportunities.json`, `reports/seo/seo_gap_summary.json` |
| `recommend.py` | Draft candidate `seoTitle`, `description`, and `tags` improvements | `opportunities.json`, `knowledge/{family}/{platform}/model.yaml` | `reports/seo/recommendations.json` |
| `safety.py` | Multi-layer guard: path guard, evidence-block freeze, stale_since gate, body-text lock | `recommendations.json` | `reports/seo/safe_recommendations.json`, `reports/seo/rejected.json`, `reports/seo/safety_summary.json` |
| `report.py` | Build human-readable reports, structured patch manifest, and pipeline run log | `safe_recommendations.json` | `reports/seo/summary.md`, `reports/seo/pages/`, `patches/seo/patch_manifest.json`, `reports/seo/pipeline_run.json` |
| `apply.py` | Perform YAML surgery on frontmatter fields listed in patch manifest | `patches/seo/patch_manifest.json`, content files | Modified content files (dry-run: diff only) |
| `compare.py` | Post-apply verification: compare two `opportunities.json` snapshots | Two `opportunities.json` files (before/after) | `reports/seo/compare_<timestamp>.json`, `reports/seo/compare_<timestamp>.md` |

### Human review workflow

Before `apply.py` can run, MEDIUM and HIGH recommendations require human approval. Use the `/seo-review` Claude command to review pending recommendations interactively:

```
/seo-review --level all --limit 20
```

This loads `safe_recommendations.json`, presents before/after diffs per page, and writes approved patches to `patches/seo/patch_manifest.json` with `requires_human_review: false`.

---

## 4. Running Locally

All commands run from the repository root.

```bash
# 0. Prerequisites
pip install pyyaml openai
export LITELLM_KEY="your-key-here"   # required for Track 2 (LLM topic signals)

# 1. Validate assets (exits non-zero if keyword data is missing or malformed)
python scripts/seo/pipeline/validate.py

# 2. Build page inventory
python scripts/seo/pipeline/inventory.py

# 3. Map GSC URLs to content files
python scripts/seo/pipeline/map_url.py

# 4. Score opportunities
python scripts/seo/pipeline/analyze.py

# 5. Generate recommendations
python scripts/seo/pipeline/recommend.py

# 6. Run safety checks
python scripts/seo/pipeline/safety.py

# 7. Generate reports and patch manifest
python scripts/seo/pipeline/report.py

# 7a. Review MEDIUM/HIGH recommendations (human gate)
#     Use the /seo-review Claude command in your IDE

# 8a. Preview changes (safe — writes nothing)
python scripts/seo/pipeline/apply.py --dry-run

# 8b. Apply changes (modifies frontmatter in content files)
python scripts/seo/pipeline/apply.py

# 9. Post-apply comparison (run 4+ weeks after apply to measure impact)
python scripts/seo/pipeline/compare.py --before reports/seo/opportunities_before.json \
                                        --after  reports/seo/opportunities.json
```

To run only a specific product family, set the `SEO_FAMILIES` environment variable before running the pipeline steps:

```bash
export SEO_FAMILIES="words,cells"
python scripts/seo/pipeline/inventory.py
# ... continue remaining steps
```

### Refreshing Schema A keywords

Schema A keywords are LLM-generated keyword sets per product family. They are refreshed automatically by the `seo-keyword-refresh.yml` workflow (monthly). To regenerate manually:

```bash
export GOOGLE_API_KEY="your-gemini-key"

# Scan KB content (original scope)
python scripts/seo/get_keywords.py content/kb.aspose.org keywords/

# Scan docs content (includes slides, 3d, email, note, diagram, cad families)
python scripts/seo/get_keywords.py content/docs.aspose.org/en keywords/

# Scan products content
python scripts/seo/get_keywords.py content/products.aspose.org/en keywords/

# Or limit to specific families
python scripts/seo/get_keywords.py content/docs.aspose.org/en keywords/ --families slides 3d email note
```

After regenerating, run `validate.py` to confirm schema integrity.

---

## 5. GitHub Actions

All three SEO workflows live in **`Aspose/aspose.org-workflows`** — not in this repo. They check out `Aspose/aspose.org` at runtime using `GH_TOKEN`, run the pipeline scripts, and push results back via pull request.

A copy of the keyword-refresh workflow template lives at `scripts/seo/workflows/seo-keyword-refresh.yml` in this repo. Copy that file into `Aspose/aspose.org-workflows/.github/workflows/` to deploy it.

### seo-keyword-refresh.yml (add to aspose.org-workflows)

Template: `scripts/seo/workflows/seo-keyword-refresh.yml`

Runs on the first Sunday of each month at 07:00 UTC (one hour after `gsc-query-collector`). Checks out `Aspose/aspose.org`, scans all three content sites (kb, docs, products) with `get_keywords.py`, runs `validate.py`, and opens a PR on `Aspose/aspose.org` if any `keywords/{family}.json` files changed.

To trigger manually (once deployed): **Aspose/aspose.org-workflows → Actions → SEO Schema A Keyword Refresh → Run workflow**

Optional inputs:
- `families` — space-separated family names to refresh (blank = all 18 defaults)
- `content_sites` — comma-separated content dirs to scan

### seo-analysis.yml (aspose.org-workflows)

The analysis workflow runs automatically every **Monday at 06:00 UTC**, one day after the `gsc-query-collector` workflow refreshes GSC data.

To trigger manually:

1. Go to [`Aspose/aspose.org-workflows`](https://github.com/Aspose/aspose.org-workflows) → **Actions** → **SEO Analysis Pipeline** → **Run workflow**
2. Optionally enter a comma-separated `families` value (e.g. `words,cells`) to limit scope
3. Leave blank to run across all families
4. The workflow uploads all outputs as an artifact named `seo-analysis-<run_id>` (retained 30 days)

### seo-apply.yml (aspose.org-workflows)

`seo-apply.yml` is **always manual** — it never runs on a schedule.

**Dry run (preview only):**

1. Go to [`Aspose/aspose.org-workflows`](https://github.com/Aspose/aspose.org-workflows) → **Actions** → **SEO Apply (Manual Gate)** → **Run workflow**
2. Enter the `artifact_run_id` from the analysis run
3. Set `dry_run` = `true`
4. The workflow prints a diff of all proposed changes; no files are modified

**Apply run (creates a PR):**

1. Same as above but set `dry_run` = `false`
2. The workflow applies patches, runs the content audit, and opens a pull request on branch `seo/<run_id>`
3. The PR title follows: `chore(seo): SEO frontmatter improvements [batch: <run_id>]`
4. Review the PR diff and `patches/seo/patch_manifest.json` before merging

---

## 6. Secrets Required

All secrets are set in **`Aspose/aspose.org-workflows`** (not in this repo).

| Secret | Used By | Notes |
|--------|---------|-------|
| `GOOGLE_API_KEY` | `seo-keyword-refresh.yml` → `get_keywords.py` | Gemini API key for Schema A keyword generation |
| `LITELLM_KEY` | `seo-analysis.yml` → `analyze.py`, `recommend.py` | LLM endpoint at `llm.professionalize.com`; degrades gracefully to Track 1-only if absent |
| `GH_TOKEN` or `REPO_TOKEN` | All three workflows — checkout, commit, PR creation | PAT with `repo` (full) scope on `Aspose/aspose.org`; used to check out the private repo and open PRs |

To set secrets via CLI:
```bash
gh secret set GOOGLE_API_KEY --repo Aspose/aspose.org-workflows
gh secret set LITELLM_KEY --repo Aspose/aspose.org-workflows
gh secret set GH_TOKEN --repo Aspose/aspose.org-workflows
```

---

## 7. GSC Service Account Access (Phase 0a — Complete)

All 7 subdomains now have `gsc-query-collector` service account access granted at **Restricted User** level in Google Search Console:

| Property | Status |
|----------|--------|
| www.aspose.org | Connected |
| products.aspose.org | Connected |
| reference.aspose.org | Connected |
| websites.aspose.org | Connected |
| docs.aspose.org | Connected (Phase 0a) |
| blog.aspose.org | Connected (Phase 0a) |
| kb.aspose.org | Connected (Phase 0a) |

Track 1 data will flow in on the next Sunday run of `gsc-query-collector`. HIGH opportunity pages will appear in `opportunities.json` once pages with 100+ impressions and low CTR are indexed.

---

## 8. Governance Constraints

These rules are enforced by `safety.py` and cannot be bypassed by the pipeline:

| Constraint | Enforcement point | Effect if violated |
|------------|------------------|--------------------|
| **Evidence blocks are read-only** | `safety.py` patch validator | Recommendation rejected; logged to `rejected.json` |
| **Body text is immutable** | `apply.py` YAML surgeon | Only `seoTitle`, `description`, and `tags` keys may be written; any attempt to write other keys aborts |
| **`stale_since` gate** | `safety.py` knowledge freshness check | If `model.yaml` has `stale_since != null`, all recommendations for that family are rejected until knowledge is refreshed (run S-12 → S-14) |
| **Path guard** | `safety.py` allowed-path check | Patches targeting paths outside `content/` are rejected |
| **Forbidden write paths** | `apply.py` pre-flight | `themes/`, `layouts/`, `configs/`, `AGENTS.md`, `CLAUDE.md` are hard-blocked |

These constraints implement the governance rules defined in `AGENTS.md` and `CLAUDE.md`.

---

## 9. Output Files Reference

### reports/seo/

| File | Description |
|------|-------------|
| `validation_report.json` | Pass/fail status for all keyword assets and GSC data files; lists missing or malformed inputs |
| `page_index.json` | Full inventory of all English content pages: path, frontmatter snapshot, GSC url_map join |
| `opportunities.json` | Ranked list of keyword-gap opportunities per page with Track 1 / Track 2 signal breakdown |
| `seo_gap_summary.json` | Aggregate statistics: pages analyzed, gap count by family, top missing keyword clusters |
| `recommendations.json` | Draft `seoTitle`, `description`, and `tags` for each opportunity page, with evidence citations |
| `rejected.json` | Recommendations blocked by safety.py, with rejection reason per entry |
| `safe_recommendations.json` | Recommendations that passed all safety checks; these feed report.py and apply.py |
| `safety_summary.json` | Counts of accepted vs. rejected recommendations, rejection reasons histogram |
| `summary.md` | Human-readable dashboard: top opportunities, fields changed, families covered, next steps |
| `pages/` | Per-page report files (one `.md` per affected page) showing current vs. proposed frontmatter |
| `pipeline_run.json` | Machine-readable audit log for each pipeline run: timestamp, stage status, artifact sizes, opportunity counts, patch count, GSC match rate |
| `compare_<timestamp>.json` | Post-apply delta: per-page opportunity level changes (IMPROVED / REGRESSED / UNCHANGED) |
| `compare_<timestamp>.md` | Human-readable version of the compare delta report |

### patches/seo/

| File | Description |
|------|-------------|
| `patch_manifest.json` | Structured list of every proposed frontmatter change: file path, field, old value, new value, evidence citation. Approved patches have `requires_human_review: false`. This is the authoritative input to `apply.py`. |
