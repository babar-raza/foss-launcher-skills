<!-- CONTRACT: scripts/pipeline/commands/ops/update_product_registry.py
     postcondition: writes data/products.json with one entry per discovered {family}/{platform} pair
     postcondition: each entry contains repo_name, repo_url, clone_url, active flag, discovered_via
     postcondition: --dry-run mode prints a summary table and exits 0 without modifying data/products.json
     verified: 2026-04-01
-->
# S-68: Update Registry - Discover and Register FOSS Repositories

**Arguments**: $ARGUMENTS
Optional format: `[--token TOKEN] [--local-only] [--force] [--dry-run]`

## Purpose

Scan all 26 Aspose GitHub organisations (`aspose-{family}-foss`) for FOSS repositories,
classify each repo by family and platform, and write the canonical product registry to
`data/products.json`. This file is the source of truth used by `clone_cache.py` (for
auto-cloning) and `refresh_knowledge.py` (for batch knowledge refresh).

Run this skill whenever:
- A new Aspose family org is created on GitHub
- A new repo is pushed to an existing org
- You need to verify the current state of all active products
- `clone_cache.py` fails with "clone_url not found" for a product

`data/products.json` is the durable output. `org_scanner.py` returns data only in
memory; the only persisted record of discovery results is this file.

---

## Modes

| Flag | Behaviour |
|------|-----------|
| *(none)* | Scan all 26 GitHub orgs; merge with `knowledge/` dirs; write registry |
| `--dry-run` | Print discovered repos as a summary table; do NOT write `data/products.json` |
| `--local-only` | Skip GitHub API; derive registry from `knowledge/{family}/{platform}/` dirs only |
| `--force` | Overwrite `active` status even for repos already in the registry |
| `--token TOKEN` | GitHub PAT (falls back to `GH_TOKEN`, then `GITHUB_TOKEN`) |

---

## Pre-conditions

1. `.venv` is activated (`source .venv/Scripts/activate` on Windows or `.venv/bin/activate` on Unix)
2. `requests>=2.28` installed (`pip show requests`)
3. `GH_TOKEN` set to a **classic** PAT, or passed via `--token` (required for live GitHub
   scan; not required for `--local-only`). `GITHUB_TOKEN` holds a fine-grained PAT that all
   25 `aspose-*-foss` orgs reject with HTTP 403 (>366-day-lifetime policy, ST-058) — it is
   only a last-resort fallback in the resolution order.

   Exit codes: 0 = registry written; 1 = `--reconcile` found a MISSING/STALE signal;
   2 = no credential, or the scan reached no org — the tracked `data/products.json` is left
   UNCHANGED rather than rewritten from unverified data (ST-058).
4. `scripts/pipeline/lib/org_scanner.py` exists
5. `data/` directory exists (or will be created automatically)

---

## Steps

> **Skill context gate** — run before step 1:
> ```bash
> PYTHONPATH=scripts/pipeline .venv/Scripts/python scripts/pipeline/commands/governance/skill_context.py begin --skill S-68 --scope "*"
> ```


1. **Parse arguments**: Extract flags from $ARGUMENTS. Default to full GitHub scan mode.

2. **Resolve org list**: Read `_DEFAULT_ORGS` from `update_product_registry.py` (26 entries,
   `aspose-{family}-foss` pattern). This list is overrideable via `ASPOSE_ORG` env var
   (comma-separated). The `--org` CLI flag is also accepted.

3. **Run discovery**:
   ```bash
   .venv/Scripts/python scripts/pipeline/commands/ops/update_product_registry.py [--token $GH_TOKEN] [--dry-run] [--local-only] [--force]
   ```

   - **GitHub mode** (default): Calls `org_scanner.scan_orgs()` for each of the 26 orgs.
     Each repo name is matched against two patterns:
     - New: `Aspose.{Family}-FOSS-for-{Platform}` (e.g. `Aspose.3D-FOSS-for-Python`)
     - Legacy: `aspose-{family}-{platform}` (e.g. `aspose-3d-python`)
     Non-matching repos are silently skipped.
   - **Local mode** (`--local-only`): Walks `knowledge/{family}/{platform}/` directories.
     Entries have empty `repo_url`/`clone_url` and `discovered_via: knowledge_dir`.
   - Both modes run together by default: GitHub results take precedence; local entries
     fill gaps for products not yet on GitHub.

4. **Check output** (dry-run only): Print a table of `family | platform | repo_name | active`.
   Exit without modifying `data/products.json`. STOP here if `--dry-run` was requested.

5. **Write registry**: Merge discovered products with existing `data/products.json` entries
   and write atomically. Summarise counts:
   ```
   OK  Wrote N products to data/products.json
       active=A  inactive=I
   ```

6. **Report new products**: Compare result against prior registry. For each newly added
   `{family}/{platform}` entry, note: "New product discovered: {family}/{platform} — run
   `/knowledge-bootstrap {family} {platform}` to initialise knowledge."

---

> **Skill context close** — run after the last step:
> ```bash
> PYTHONPATH=scripts/pipeline .venv/Scripts/python scripts/pipeline/commands/governance/skill_context.py end --skill S-68 --status completed
> ```

## Post-conditions

- `data/products.json` contains one entry per discovered `{family}/{platform}` pair
- Each entry has: `family`, `platform`, `repo_name`, `repo_url`, `clone_url`, `active`, `discovered_via`
- Entries are sorted by `family` then `platform` for stable diffs
- `clone_cache.py` can now resolve `clone_url` for any listed product

---

## Error handling

- **GitHub API unreachable**: `org_scanner` falls back to its cached `.json` files in
  `state_dir` if available; otherwise prints `WARN: GitHub scan failed` and continues
  with local-only discovery. Do NOT abort — partial results are acceptable.
- **`requests` not installed**: Script exits with `ERROR: requests library required`.
  Fix: `pip install requests`.
- **No results at all** (GitHub failed AND no `knowledge/` dirs exist): Print error and
  exit non-zero. Investigate network access or token validity.
- **`--dry-run` + `--local-only`**: Both flags are compatible; dry-run always wins
  (never writes).

---

## Next steps after registry update

For any newly discovered product, run in order:
1. `/knowledge-bootstrap {family} {platform}` — extract, enrich, and promote knowledge
2. `/launch-product {family} {platform}` — generate all 5-subdomain documentation
