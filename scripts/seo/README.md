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
- Emits per-page reports, a summary dashboard, and a structured patch manifest
- Applies approved patches via YAML surgery (frontmatter only)

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

---

## 3. Module Summary

| Module | Purpose | Primary Input | Primary Output |
|--------|---------|---------------|----------------|
| `validate.py` | Confirm keyword assets and GSC data are present and well-formed | `knowledge/{family}/keywords.yaml`, `reports/gsc/` | `reports/seo/validation_report.json` |
| `inventory.py` | Walk all content trees, extract frontmatter for every English index page | `content/` | `reports/seo/page_index.json` |
| `map_url.py` | Join GSC URL records to inventory entries by URL slug | `reports/seo/page_index.json`, `reports/gsc/` | Appends `url_map` key to `page_index.json` |
| `analyze.py` | Score keyword gaps; merge Track 1 and Track 2 signals | `page_index.json` (with url_map), `keywords.yaml` | `reports/seo/opportunities.json`, `reports/seo/seo_gap_summary.json` |
| `recommend.py` | Draft candidate `seoTitle`, `description`, and `tags` improvements | `opportunities.json`, `knowledge/{family}/{platform}/model.yaml` | `reports/seo/recommendations.json` |
| `safety.py` | Multi-layer guard: path guard, evidence-block freeze, stale_since gate, body-text lock | `recommendations.json` | `reports/seo/safe_recommendations.json`, `reports/seo/rejected.json`, `reports/seo/safety_summary.json` |
| `report.py` | Build human-readable reports and structured patch manifest | `safe_recommendations.json` | `reports/seo/summary.md`, `reports/seo/pages/`, `patches/seo/patch_manifest.json` |
| `apply.py` | Perform YAML surgery on frontmatter fields listed in patch manifest | `patches/seo/patch_manifest.json`, content files | Modified content files (dry-run: diff only) |

---

## 4. Running Locally

All commands run from the repository root (`D:\onedrive\Documents\GitHub\aspose.org` or wherever you cloned it).

```bash
# 0. Prerequisites
pip install pyyaml openai
export LITELLM_KEY="your-key-here"   # only needed if analyze.py falls back to Track 2

# 1. Validate assets (exits non-zero if GSC data is missing or malformed)
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

# 8a. Preview changes (safe — writes nothing)
python scripts/seo/pipeline/apply.py --dry-run

# 8b. Apply changes (modifies frontmatter in content files)
python scripts/seo/pipeline/apply.py
```

To run only a specific product family, set the `SEO_FAMILIES` environment variable before running the pipeline steps:

```bash
export SEO_FAMILIES="words,cells"
python scripts/seo/pipeline/inventory.py
# ... continue remaining steps
```

---

## 5. GitHub Actions

The SEO workflows live in **`Aspose/aspose.org-workflows`** — not in this repo. They check out `Aspose/aspose.org` at runtime, run the pipeline scripts, and push results back via pull request.

### Triggering seo-analysis.yml

The analysis workflow runs automatically every **Monday at 06:00 UTC**, one day after the `gsc-query-collector` workflow refreshes GSC data.

To trigger manually:

1. Go to [`Aspose/aspose.org-workflows`](https://github.com/Aspose/aspose.org-workflows) → **Actions** → **SEO Analysis Pipeline** → **Run workflow**
2. Optionally enter a comma-separated `families` value (e.g. `words,cells`) to limit scope
3. Leave blank to run across all families
4. The workflow uploads all outputs as an artifact named `seo-analysis-<run_id>` (retained 30 days) to `aspose.org-workflows`

### Triggering seo-apply.yml

`seo-apply.yml` is **always manual** — it never runs on a schedule.

**Dry run (preview only):**

1. Go to [`Aspose/aspose.org-workflows`](https://github.com/Aspose/aspose.org-workflows) → **Actions** → **SEO Apply (Manual Gate)** → **Run workflow**
2. Enter the `artifact_run_id` from the analysis run (the numeric GitHub run ID from `aspose.org-workflows`)
3. Set `dry_run` = `true`
4. The workflow prints a diff of all proposed changes; no files are modified

**Apply run (creates a PR):**

1. Same as above but set `dry_run` = `false`
2. The workflow applies patches, runs the content audit, and opens a pull request on branch `seo/<run_id>` in **this repo** (`Aspose/aspose.org`)
3. The PR title follows the pattern: `chore(seo): SEO frontmatter improvements [batch: <run_id>]`
4. Review the PR diff and `patches/seo/patch_manifest.json` before merging

---

## 6. Secrets Required

Secrets must be set in **`Aspose/aspose.org-workflows`** (not in this repo).

| Secret | Used By | Notes |
|--------|---------|-------|
| `LITELLM_KEY` | `seo-analysis.yml` → `analyze.py`, `recommend.py` | LLM endpoint at `llm.professionalize.com`; only consumed when Track 2 (LLM topic signals) is active. The pipeline degrades gracefully to Track 1-only if the key is absent and no new-content pages are in scope. |
| `GH_TOKEN` or `REPO_TOKEN` | Both workflows — checkout, artifact download, PR creation | PAT with `repo` (full) scope on `Aspose/aspose.org`. Used to check out this repo cross-org, download artifacts, and open PRs. Set `GH_TOKEN`; `REPO_TOKEN` is the fallback. |

To set secrets via CLI:
```bash
gh secret set LITELLM_KEY --repo Aspose/aspose.org-workflows
gh secret set GH_TOKEN --repo Aspose/aspose.org-workflows
```

---

## 7. Phase 0a Requirement — GSC Service Account

**The pipeline produces no Track 1 data until this step is complete.**

For each subdomain that serves content, the GSC service account used by `gsc-query-collector` must be granted **Restricted User** (or higher) access in Google Search Console:

| Property | URL |
|----------|-----|
| blog.aspose.org | `https://blog.aspose.org/` |
| docs.aspose.org | `https://docs.aspose.org/` |
| kb.aspose.org | `https://kb.aspose.org/` |
| reference.aspose.org | `https://reference.aspose.org/` |

Steps:
1. Open [Google Search Console](https://search.google.com/search-console)
2. Select the property
3. Settings → Users and permissions → Add user
4. Enter the service account email (find it in the `gsc-query-collector` workflow secrets or GCP IAM)
5. Set permission level to **Restricted** (read-only is sufficient)
6. Repeat for all four properties

Until access is granted, `validate.py` will warn about missing GSC exports, and the pipeline will operate in Track 2-only mode.

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

### patches/seo/

| File | Description |
|------|-------------|
| `patch_manifest.json` | Structured list of every proposed frontmatter change: file path, field, old value, new value, evidence citation. This is the authoritative input to `apply.py`. |
