---
name: link-validate
id: S-65
description: >
  Validate cross-site internal links in content files; report BROKEN links where
  the target slug does not exist locally. Uses config.yaml site keys to determine
  valid link targets.
args: "{family} {platform} | all | --files {file1.md} ..."
---

# S-65: Link Validate — Cross-Site Internal Link Validation

**Arguments**: $ARGUMENTS
Expected format:
- `{family} {platform}` — validate all content for this product
- `all` — validate all content in the repo
- `--files {file1.md} [file2.md ...]` — validate specific files

## Purpose

Validate cross-site internal links in content files. Finds links pointing to other
site sections (docs → kb, blog → docs, reference → docs, etc.) and reports BROKEN
links where the target slug does not exist in the local content directory.

Use before publishing to catch stale cross-site links that would result in 404s
in production.

The set of valid site sections is determined by the `sites` keys in `config.yaml`
(e.g., `docs`, `blog`, `kb`, `reference`, `products`). No site-specific URLs are
hardcoded in this skill.

## Pre-conditions

None. This skill works from the local content directory only.

> **Optional context gate** — if `scripts/skill_context.py` exists, run before step 1:
> ```bash
> python scripts/skill_context.py begin --skill S-65 --scope "{target}"
> ```

## Steps

### Step 1: Build slug index

Build an index of all slugs that currently exist in the local content directories.
A slug is the content path relative to the site root (e.g., `/docs/words/python/getting-started/`).

Read the site paths from `config.yaml` `sites` section. Scan those directories for
all `.md` files and compute their slugs.

If `scripts/link_validator.py` exists, use it directly:

```bash
# Product-wide:
python scripts/link_validator.py {family} {platform}

# All content:
python scripts/link_validator.py all

# Specific files:
python scripts/link_validator.py --files path/to/file.md
```

### Step 2: Extract links

For each target `.md` file, extract all internal links (links that point to paths
matching any site section in `config.yaml`). Strip fragment anchors (`#section`) and
query parameters before matching.

### Step 3: Validate each link

For each internal link:
- Look up the target path in the slug index
- If found: PASS
- If not found: BROKEN

Locale variants (e.g., `/fr/`, `/ar/`) are included in the slug index — a link to
a locale page resolves correctly if the locale file exists.

### Step 4: Review BROKEN findings

For each BROKEN link:
1. **Update the URL** if the target page exists at a different path
2. **Remove the link** if the target page no longer exists
3. **Create the missing page** if the link should exist (use appropriate generation skill)
4. **Accept as expected** if the target page will be created shortly — document this

### Step 5: Save report

```bash
# JSON output for CI integration:
python scripts/link_validator.py {family} {platform} --json \
  > reports/link-validation/{family}-{platform}-{timestamp}.json
```

If no script is available: write a plain Markdown report to
`reports/link-validation/{family}-{platform}-{timestamp}.md`.

> **Optional context close** — if `scripts/skill_context.py` exists, run after the last step:
> ```bash
> python scripts/skill_context.py end --skill S-65 --status completed
> ```

## Post-conditions

- All BROKEN links are documented or fixed
- Report saved to `reports/link-validation/`
- No new BROKEN cross-site links remain in modified content files

## Exit codes

| Code | Meaning |
|---|---|
| 0 | No broken links found |
| 1 | One or more broken links found |

## Notes

- This skill validates links that exist in the **local content directory** only.
  It cannot validate external links (e.g., GitHub, documentation.org URLs).
- Link patterns to check are derived from `config.yaml sites` section — add new
  site sections there, not in this skill.
- Fragment anchors (`#section-name`) are stripped before validation.
