# S-69: Getting Started — Bootstrap the Repo Environment

**Arguments**: $ARGUMENTS
Optional format: `{family} {platform}` to bootstrap a specific product. Omit to see all steps.

## Purpose

Answer "I just cloned the repo — what do I do?" Covers the full 7-step setup from a
fresh clone through a verified, content-ready environment. Follow steps in order;
each step depends on the previous.

---

## Step 1: Python environment

Install all pipeline dependencies:

```bash
pip install -r scripts/requirements.txt
```

Key packages required:

| Package | Minimum version |
|---------|----------------|
| tree-sitter | >= 0.25 |
| tree-sitter-language-pack | >= 0.13 |
| pyyaml | >= 6.0 |
| requests | >= 2.28 |

Verify with `pip show tree-sitter pyyaml requests`.

Alternatively use the install script:
```bash
bash install.sh      # Unix/macOS
./install.ps1        # Windows PowerShell
```

---

## Step 2: Credentials

Create `.env` at the repo root (already in `.gitignore` — never commit it):

```
GITHUB_TOKEN=<personal access token with repo read scope>
```

`GITHUB_TOKEN` is required for product registry scanning and FOSS repo cloning (Steps 3–4).

---

## Step 3: Configure content repo path

Set the path to your external content repository before running any content-writing skills:

```bash
export CONTENT_REPO_PATH=/path/to/your/content-repo
```

Or set `content_root` in `config.yaml` at the repo root.

Verify:
```bash
python scripts/check_setup.py
```

---

## Step 4: Populate product registry

Discover FOSS repositories and update the product list:

```bash
python scripts/discover.py --token $GITHUB_TOKEN
```

This uses the discover-products skill (S-39). Run after adding new products.
Alternatively scan by family:

```bash
python scripts/discover.py --family 3d --token $GITHUB_TOKEN
```

---

## Step 5: Bootstrap knowledge for a product

Run the pipeline to extract knowledge from the FOSS source repo:

```bash
python scripts/pipeline/commands/knowledge/refresh_knowledge.py --family {family} --platform {platform}
```

**Expected outputs after completion:**

- `knowledge/{family}/{platform}/scout/` — raw extraction artifacts
- `knowledge/{family}/{platform}/merged/model.yaml` — product model
- `knowledge/{family}/{platform}/merged/api_surface.json` — API surface
- `knowledge/{family}/{platform}/merged/claims.json` — verifiable claims

To bootstrap all products at once:

```bash
python scripts/pipeline/commands/knowledge/refresh_knowledge.py --all
```

---

## Step 5b: Install git hooks

Install the pre-commit and commit-msg hooks to enforce governance on every commit:

```bash
bash scripts/install-hooks.sh
```

This installs:
- `pre-commit` — runs `validate_skills.py` + sync checks on staged skill files
- `commit-msg` — enforces `Skills invoked:` declaration on content commits

Verify installation:
```bash
ls -la .git/hooks/pre-commit .git/hooks/commit-msg
```

---

## Step 6: Verify environment is healthy

Run the setup checker:

```bash
python scripts/check_setup.py --family {family} --platform {platform}
```

Quick batch check across all configured products:

```bash
python scripts/pipeline/commands/content/audit.py --all
```

Expected result: `PASS` or a findings list with severity levels.

---

## Step 7: Read governance before touching content

Do not edit any content page before completing these checks:

1. Read `AGENTS.md` — authoritative agent governance rules
2. Read `knowledge/{family}/{platform}/merged/model.yaml`:
   - Confirm `stale_since: null` — if not null, run the staleness workflow (S-12 → S-14) first
   - Note `api_confidence` level — low confidence means content claims need extra care
3. Check `CLAUDE.md` for the content paths and forbidden write rules
4. Only then proceed to content work

---

## Notes for agents

- Never skip Step 6 before editing content pages — knowledge freshness is a hard requirement.
- If `stale_since != null` in `model.yaml`, run S-12 (knowledge-diff) → S-13 (stale-detect) → S-14 (knowledge-update) before any content edits.
- The `runs/` directory is git-ignored; FOSS clones are never committed.
- For production content work, always verify knowledge freshness with `/stale-detect {family} {platform}` (S-13) before writing.
