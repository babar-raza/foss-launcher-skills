# S-64: Getting Started - Bootstrap the Repo Environment

**Arguments**: $ARGUMENTS
Optional format: `{family} {platform}` to bootstrap a specific product. Omit to see all steps.

## Purpose

Answer "I just cloned the repo - what do I do?" Covers the full 7-step setup from a
fresh clone through a verified, content-ready environment. Follow steps in order;
each step depends on the previous.

---

## Step 1: Python environment

Create and activate the repo virtual environment, then install all pipeline dependencies:

```bash
python -m venv .venv
source .venv/Scripts/activate   # Windows (Git Bash)
# source .venv/bin/activate     # Unix / macOS
.venv/Scripts/pip install -r scripts/requirements.txt
```

Key packages required:

| Package | Minimum version |
|---------|----------------|
| tree-sitter | >= 0.25 |
| tree-sitter-language-pack | >= 0.13 |
| tree-sitter-c-sharp | >= 0.23 |
| pyyaml | >= 6.0 |
| requests | >= 2.28 |

Verify with `.venv/Scripts/pip show tree-sitter pyyaml requests`.

> **All subsequent steps assume `.venv` is active.** If starting a new shell, re-activate first.

---

## Step 2: Credentials

Create `.env` at the repo root (already in `.gitignore` - never commit it):

```
GITHUB_TOKEN=<personal access token with repo read scope>
PROFESSIONALIZE_API_KEY=<key for LLM embeddings - optional, TF-IDF fallback used if absent>
```

`PROFESSIONALIZE_API_KEY` is optional. All embedding operations fall back to TF-IDF
automatically when the key is absent. `GITHUB_TOKEN` is required for Steps 3 and 4.

---

## Step 3: Populate product registry

Write clone URLs into `data/products.json` for all active products:

```bash
.venv/Scripts/python scripts/pipeline/update_product_registry.py --token $GITHUB_TOKEN
```

This step is required before cloning FOSS source repos. Without it the product
registry lacks clone URLs and subsequent steps cannot locate the correct repos.

---

## Step 4: Clone FOSS source repos

FOSS repos auto-clone the first time you run scout (Step 5). To pre-clone manually:

```bash
# Run from scripts/pipeline/ directory
.venv/Scripts/python -c "from core.clone_cache import ensure_clone; ensure_clone('{family}','{platform}')"
```

Replace `{family}` and `{platform}` with the product you are working on (e.g. `3d`, `python`).
Clones land at: `runs/.clone_cache/aspose_{family}_{platform}/`

The `runs/` directory is git-ignored; FOSS clones are local only.

---

## Step 5: Bootstrap knowledge for a product

Run the four-stage pipeline to extract, enrich, promote, and index knowledge:

```bash
cd scripts/pipeline
../../.venv/Scripts/python scout.py {family} {platform} ../../runs/.clone_cache/aspose_{family}_{platform}/ ../../knowledge/{family}/{platform}/scout/
../../.venv/Scripts/python enrich.py {family} {platform}
../../.venv/Scripts/python promote.py {family} {platform}
../../.venv/Scripts/python index.py {family} {platform}
```

**Expected outputs after completion:**

- `knowledge/{family}/{platform}/scout/` - raw extraction artifacts
- `knowledge/{family}/{platform}/scout/enriched_claims.json` - LLM-enriched claims
- `knowledge/{family}/{platform}/merged/model.yaml` - product model with confidence scores
- `knowledge/{family}/{platform}/merged/api_surface.json` - discovered API surface
- `knowledge/{family}/{platform}/merged/claims.json` - verifiable claims
- `knowledge/{family}/{platform}/merged/index.json` - searchable index

To bootstrap all products at once:

```bash
.venv/Scripts/python scripts/pipeline/refresh_knowledge.py --all --check
```

---

## Step 5b: Install pre-commit hook

Install the content audit pre-commit hook to enforce API accuracy on every commit:

```bash
cp scripts/pre-commit-audit.sh .git/hooks/pre-commit
chmod +x .git/hooks/pre-commit
```

This hook runs `audit.py` on staged content files and blocks commits with API accuracy failures.

Also install the commit-msg hook to enforce `Skills invoked:` declaration on content commits (AGENTS.md §10):

```bash
cp scripts/commit-msg-skills.sh .git/hooks/commit-msg
chmod +x .git/hooks/commit-msg
```

**WARN**: If `.git/hooks/commit-msg` is absent or not executable, content commits will not enforce
the `Skills invoked:` field required by AGENTS.md §10. Verify with:

```bash
ls -la .git/hooks/commit-msg
```

If missing, re-run the install commands above.

---

## Step 5c: Provenance backfill (fresh-clone only)

On a fresh clone, locale files translated before the provenance system was introduced lack
a `provenance:` block. Run the backfill to assign conservative defaults:

```bash
.venv/Scripts/python scripts/pipeline/provenance_backfill.py
```

This is safe to re-run at any time (idempotent — files that already have a provenance block
are skipped). After the backfill, all files have `auto_updatable: true` and
`translation_origin: unknown` as their conservative baseline. Human-authored files should be
updated manually to `auto_updatable: false` after running `/register-human-content` (S-66).

---

## Step 6: Verify environment is healthy

Run the audit tool against your product:

```bash
.venv/Scripts/python scripts/pipeline/audit.py {family} {platform}
```

Expected result: `PASS` or a findings list with severity levels.

If `model.yaml` shows `api_confidence: low`, re-run scout with more verbose logging
(add `--verbose` flag if supported, or inspect `scout/` artifacts manually).

Quick batch check across all products:

```bash
.venv/Scripts/python scripts/pipeline/audit.py all --json | .venv/Scripts/python -c "import json,sys; r=json.load(sys.stdin); print(f'{sum(1 for f in r if f[\"level\"]==\"FAIL\")} FAILs found')"
```

---

## Step 7: Read governance before touching content

Do not edit any content page before completing these checks:

1. Read `AGENTS.md` - authoritative agent governance rules
2. Read `knowledge/{family}/{platform}/merged/model.yaml`:
   - Confirm `stale_since: null` - if not null, run the staleness workflow (S-12 -> S-14) first
   - Note `api_confidence` level - low confidence means content claims need extra care
3. Check the relevant content path in `CLAUDE.md` for the target site
4. Only then proceed to content work

---

## Notes for agents

> **Authoritative source**: The governance rules below are also documented in `AGENTS.md` §2
> (Read Order) and §9 (Maintenance Workflow). Those sections take precedence if any
> discrepancy exists. These notes are a quick reference for first-time onboarding only.

- Never skip Step 6 before editing content pages — knowledge freshness is a hard requirement.
- If `stale_since != null` in `model.yaml`, run S-12 (knowledge-diff) → S-13 (stale-detect) → S-14 (knowledge-update) before any content edits.
- `PROFESSIONALIZE_API_KEY` is optional; TF-IDF fallback is transparent to all consuming skills.
- The `runs/` directory is git-ignored; FOSS clones are never committed.
- For production content work, always verify knowledge freshness with `/stale-detect {family} {platform}` (S-13) before writing.
- Cross-product refresh: `.venv/Scripts/python scripts/pipeline/refresh_knowledge.py --all --check`
