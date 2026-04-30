# audit/ — Content API Accuracy Verification

Verifies that published content pages only reference API members that exist in the merged knowledge model. Called by the `commands/content/audit.py` CLI entry point.

## CLI Usage

All commands must be run from the repo root.

```bash
# Single product
python scripts/pipeline/commands/content/audit.py slides python

# All products
python scripts/pipeline/commands/content/audit.py all

# Specific files
python scripts/pipeline/commands/content/audit.py --files content/docs.aspose.org/en/3d/python/index.md

# Machine-readable JSON output
python scripts/pipeline/commands/content/audit.py all --json

# Skip evidence frontmatter checks
python scripts/pipeline/commands/content/audit.py 3d python --no-evidence

# Check snippet coverage
python scripts/pipeline/commands/content/audit.py 3d python --check-snippets

# Stop on first FAIL product
python scripts/pipeline/commands/content/audit.py all --fail-fast
```

Exit code: `0` if no FAIL findings; `1` if any FAIL findings.

## Modules

### runner.py — Core Audit Orchestration

Provides `audit_product()`, `audit_files()`, and `main()`. Orchestrates the full audit workflow.

**`audit_product(family, platform, check_evidence=True, check_snippets=False) -> list`**
- Discovers content files via `knowledge_core.discover_content()`
- Calls `extract_tokens()` + `verify_tokens()` for each file
- Optionally verifies `evidence:` frontmatter block via `verify_evidence()`
- Calls `verify_internal_links()` for all files
- Returns `list[Finding]`

**`audit_files(file_paths, check_evidence=True, check_snippets=False) -> list`**
- Infers product from file path
- Applies same verification as `audit_product()` on a per-file basis
- Returns `list[Finding]`

### links.py — Internal Link Verification

**`verify_internal_links(filepath) -> list[Finding]`**

Validates markdown links in content pages. Checks that cross-page relative links resolve to existing files within the same subdomain content tree.

### snippets.py — Snippet Coverage Verification

**`verify_snippet_coverage(filepath, knowledge) -> list[Finding]`**

Checks whether API classes mentioned in a content page have corresponding code examples in the snippet index. Emits INFO findings for classes with no snippet coverage.

### reports.py — Report Formatting and Quality Trend

Formats audit findings and manages the quality trend JSONL.

| Function | Description |
|----------|-------------|
| `report_text(findings, products)` | Human-readable audit report (Markdown) |
| `report_json(findings, products)` | Machine-readable JSON report |
| `_append_quality_trend(products_summary)` | Append per-run stats to `reports/audit/quality_trend.jsonl` |
| `_write_quality_baseline(products_summary)` | Write baseline file for regression detection |
| `_prune_quality_trend()` | Keep at most `QUALITY_TREND_MAX_ENTRIES` (180) entries |

Reports are written to `reports/audit/batch-audit-{YYYYMMDD}.md`.

## Finding Levels

| Level | Meaning |
|-------|---------|
| `FAIL` | API token (class, method, property, enum) not found in `api_surface.json` |
| `WARN` | Probable match but unverified (e.g., method from parent class, fuzzy match) |
| `INFO` | Advisory: missing snippet coverage, missing evidence block |

## Inputs and Outputs

**Inputs:**
- Content pages: `content/docs.aspose.org/en/{family}/{platform}/**/*.md`
- Knowledge model: `knowledge/{family}/{platform}/merged/api_surface.json`
- Knowledge index: `knowledge/{family}/{platform}/merged/index.json`

**Outputs:**
- `list[Finding]` (in-process)
- `reports/audit/batch-audit-{YYYYMMDD}.md` (text report)
- `reports/audit/quality_trend.jsonl` (trend tracking, batch mode only)

## Used By

- **S-23 content-check skill** — pre-commit quality gate
- **CI pipeline** — automated content regression detection
- `attach_evidence.py` — pages with FAIL findings are skipped for evidence attachment
