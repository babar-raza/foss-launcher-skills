# Getting Started — Bootstrap the Repo Environment

**Arguments**: $ARGUMENTS
Optional format: `{family} {platform}` to bootstrap a specific product. Omit to see all steps.

## Purpose
Answer "I just cloned the repo — what do I do?" Covers the full 7-step setup from a
fresh clone through a verified, content-ready environment. Follow steps in order;
each step depends on the previous.

---

## Step 1: Python environment

Install all pipeline dependencies from repo root:

```bash
pip install -r scripts/requirements.txt
```

Key packages required:

| Package | Minimum version |
|---------|----------------|
| tree-sitter | ≥ 0.25 |
| tree-sitter-language-pack | ≥ 0.13 |
| tree-sitter-c-sharp | ≥ 0.23 |
| pyyaml | ≥ 6.0 |
| requests | ≥ 2.28 |

Verify with `pip show tree-sitter pyyaml requests`.

---

## Step 2: Credentials

Create `.env` at the repo root (already in `.gitignore` — never commit it):

```
GITHUB_TOKEN=<personal access token with repo read scope>
PROFESSIONALIZE_API_KEY=<key for LLM embeddings — optional, TF-IDF fallback used if absent>
```

`PROFESSIONALIZE_API_KEY` is optional. All embedding operations fall back to TF-IDF
automatically when the key is absent. `GITHUB_TOKEN` is required for Steps 3 and 4.

---

## Step 3: Populate product registry

Write clone URLs into `data/products.json` for all active products:

```bash
python scripts/pipeline/update_product_registry.py --token $GITHUB_TOKEN
```

This step is required before cloning FOSS source repos. Without it the product
registry lacks clone URLs and subsequent steps cannot locate the correct repos.

---

## Step 4: Clone FOSS source repos

FOSS repos auto-clone the first time you run scout (Step 5). To pre-clone manually:

```bash
# Run from scripts/pipeline/ directory
python -c "from core.clone_cache import ensure_clone; ensure_clone('{family}','{platform}')"
```

Replace `{family}` and `{platform}` with the product you are working on (e.g. `3d`, `python`).
Clones land at: `runs/.clone_cache/aspose_{family}_{platform}/`

The `runs/` directory is git-ignored; FOSS clones are local only.

---

## Step 5: Bootstrap knowledge for a product

Run the three-stage pipeline to extract, merge, and index knowledge:

```bash
cd scripts/pipeline
python scout.py {family} {platform} ../../runs/.clone_cache/aspose_{family}_{platform}/ ../../knowledge/{family}/{platform}/scout/
python merge.py {family} {platform}
python index.py {family} {platform}
```

**Expected outputs after completion:**

- `knowledge/{family}/{platform}/scout/` — raw extraction artifacts
- `knowledge/{family}/{platform}/merged/model.yaml` — product model with confidence scores
- `knowledge/{family}/{platform}/merged/api_surface.json` — discovered API surface
- `knowledge/{family}/{platform}/merged/claims.json` — verifiable claims
- `knowledge/{family}/{platform}/merged/index.json` — searchable index

To bootstrap all products at once:

```bash
python scripts/pipeline/refresh_knowledge.py --all --check
```

---

## Step 6: Verify environment is healthy

Run the audit tool against your product:

```bash
python scripts/pipeline/audit.py {family} {platform}
```

Expected result: `PASS` or a findings list with severity levels.

If `model.yaml` shows `api_confidence: low`, re-run scout with more verbose logging
(add `--verbose` flag if supported, or inspect `scout/` artifacts manually).

Quick batch check across all products:

```bash
python scripts/pipeline/audit.py all --json | python -c "import json,sys; r=json.load(sys.stdin); print(f'{sum(1 for f in r if f[\"level\"]==\"FAIL\")} FAILs found')"
```

---

## Step 7: Read governance before touching content

Do not edit any content page before completing these checks:

1. Read `AGENTS.md` — authoritative agent governance rules
2. Read `knowledge/{family}/{platform}/merged/model.yaml`:
   - Confirm `stale_since: null` — if not null, run the staleness workflow (S-12 → S-14) first
   - Note `api_confidence` level — low confidence means content claims need extra care
3. Check the relevant content path in `CLAUDE.md` for the target site
4. Only then proceed to content work

---

## Notes for agents

- Never skip Step 6 before editing content pages
- If `stale_since != null` in `model.yaml`, run S-12 (knowledge-diff) → S-13 (stale-detect) → S-14 (knowledge-update) before any content edits
- `PROFESSIONALIZE_API_KEY` is optional; TF-IDF fallback is transparent to all consuming skills
- The `runs/` directory is git-ignored; FOSS clones are never committed
- For production content work, always verify knowledge freshness with `/stale-detect {family} {platform}` (S-13) before writing
- Cross-product refresh: `python scripts/pipeline/refresh_knowledge.py --all --check`
