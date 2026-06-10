# S-73: Update Registry — Discover and Register FOSS Repositories

**Arguments**: $ARGUMENTS
Optional format: `[--token TOKEN] [--local-only] [--force] [--dry-run]`

> **Note**: foss-launcher uses `discover-products` (S-39) as its primary product
> discovery workflow. This skill (`update-registry`) is the parallel capability
> ported from aspose.org for operators who need the full Aspose org-scanner flow.

## Purpose

Scan Aspose GitHub organisations (`aspose-{family}-foss`) for FOSS repositories,
classify each repo by family and platform, and write the product registry. This file
is the source of truth used by `clone_cache.py` (for auto-cloning) and
`refresh_knowledge.py` (for batch knowledge refresh).

Run this skill whenever:
- A new Aspose family org is created on GitHub
- A new repo is pushed to an existing org
- You need to verify the current state of all active products
- `clone_cache.py` fails with "clone_url not found" for a product

---

## Modes

| Flag | Behaviour |
|------|-----------|
| *(none)* | Scan all GitHub orgs; merge with `knowledge/` dirs; write registry |
| `--dry-run` | Print discovered repos as a summary table; do NOT write registry |
| `--local-only` | Skip GitHub API; derive registry from `knowledge/{family}/{platform}/` dirs only |
| `--force` | Overwrite `active` status even for repos already in the registry |
| `--token TOKEN` | GitHub PAT (alternative to `GITHUB_TOKEN` env var) |

---

## Pre-conditions

1. `requests>=2.28` installed (`pip show requests`)
2. `GITHUB_TOKEN` set in `.env` or passed via `--token` (required for live GitHub scan;
   not required for `--local-only`)
3. `scripts/pipeline/org_scanner.py` exists

---

## Steps

1. **Parse arguments**: Extract flags from `$ARGUMENTS`. Default to full GitHub scan mode.

2. **Resolve org list**: Read the default orgs list from `update_product_registry.py`
   (`aspose-{family}-foss` pattern). Overrideable via `ASPOSE_ORG` env var
   (comma-separated).

3. **Run discovery**:
   ```bash
   python scripts/pipeline/commands/ops/update_product_registry.py [--token $GITHUB_TOKEN] [--dry-run] [--local-only] [--force]
   ```

   - **GitHub mode** (default): Calls `org_scanner.scan_orgs()` for each org.
     Each repo name is matched against two patterns:
     - New: `Aspose.{Family}-FOSS-for-{Platform}` (e.g. `Aspose.3D-FOSS-for-Python`)
     - Legacy: `aspose-{family}-{platform}` (e.g. `aspose-3d-python`)
     Non-matching repos are silently skipped.
   - **Local mode** (`--local-only`): Walks `knowledge/{family}/{platform}/` directories.
     Entries have empty `repo_url`/`clone_url` and `discovered_via: knowledge_dir`.
   - Both modes run together by default: GitHub results take precedence; local entries
     fill gaps for products not yet on GitHub.

4. **Merge results**: Merge discovered repos with any existing registry entries.
   - New discoveries: add with `active: true`
   - Existing entries: update `repo_url`/`clone_url`; do NOT change `active` flag unless `--force`
   - Removed repos: mark `active: false` (never delete)

5. **Write registry**: Save updated registry to disk (path from `configs/families.yaml`
   or the script's configured output path).

6. **Summary report**:
   ```
   Registry updated:
     New entries:     N
     Updated entries: N
     Skipped (no change): N
     Inactive (removed from GitHub): N
   ```

---

## Relationship to discover-products (S-39)

| Skill | Scope | Output | When to use |
|-------|-------|--------|-------------|
| `discover-products` (S-39) | GitHub org scanner via `scripts/discover.py` | Updates `configs/families.yaml` | Normal foss-launcher workflow |
| `update-registry` (S-73) | Full Aspose org scanner via `scripts/pipeline/commands/ops/update_product_registry.py` | Updates product registry JSON | When you need the full 26-org scan or explicit `data/products.json` output |

For most foss-launcher operations, use S-39 (discover-products). Use this skill when
the full Aspose org scanner is required or when operating in a context that expects the
`data/products.json` registry format.

---

## Post-conditions

- Registry file updated with all active FOSS repos
- Each entry has: `family`, `platform`, `repo_name`, `repo_url`, `clone_url`, `active`, `discovered_via`
- `clone_cache.py` can resolve all active entries

## Error handling

| Error | Resolution |
|-------|-----------|
| `GITHUB_TOKEN` not set | Pass `--token` flag or set env var; or use `--local-only` |
| Rate limit exceeded | Wait and retry; or use `--local-only` for cached results |
| Org not found | Verify org name pattern; check `ASPOSE_ORG` override |
| Script not found | Verify `scripts/pipeline/commands/ops/update_product_registry.py` exists |
