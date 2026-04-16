# S-65: Link Validate — Cross-Subdomain Link Validation

**Arguments**: $ARGUMENTS
Expected format: `{family} {platform}` | `all` | `--files file1.md ...`

## Purpose

Validate cross-subdomain internal links in content files. Finds links pointing to
other aspose.org subdomains (docs → kb, blog → docs, etc.) and reports BROKEN links
where the target slug does not exist in the local content directory.

Use before publishing to catch stale cross-site links that would result in 404s on production.

## Pre-conditions

None. This skill works from the local content directory only.

## Steps

> **Skill context gate** — run before step 1:
> ```bash
> PYTHONPATH=scripts/pipeline .venv/Scripts/python scripts/pipeline/skill_context.py begin --skill S-65 --scope "*"
> ```


### Step 1: Run validation for one product

```bash
.venv/Scripts/python scripts/pipeline/link_validator.py {family} {platform}
```

Or for specific files:
```bash
.venv/Scripts/python scripts/pipeline/link_validator.py --files path/to/file.md
```

Or for all content:
```bash
.venv/Scripts/python scripts/pipeline/link_validator.py all
```

### Step 2: Review BROKEN findings

Each BROKEN finding shows:
- Source file containing the broken link
- Full URL of the broken link
- Target subdomain and path that was not found

### Step 3: Fix or accept each finding

For each BROKEN link:
1. **Update the URL** if the target page exists at a different path
2. **Remove the link** if the target page no longer exists
3. **Create the missing page** if the link should exist (use appropriate page generation skill)
4. **Accept as expected** if the target page will be created shortly — document in your PR

### Step 4: JSON output for CI integration

```bash
.venv/Scripts/python scripts/pipeline/link_validator.py {family} {platform} --json > reports/link-validation/{family}-{platform}-{timestamp}.json
```

> **Skill context close** — run after the last step:
> ```bash
> PYTHONPATH=scripts/pipeline .venv/Scripts/python scripts/pipeline/skill_context.py end --skill S-65 --status completed
> ```

## Post-conditions

- BROKEN links are documented or fixed
- Report saved to `reports/link-validation/{family}-{platform}-{timestamp}.json`
- No new BROKEN cross-subdomain links remain in modified content files

## Exit codes

| Code | Meaning |
|------|---------|
| 0 | No broken links found |
| 1 | One or more broken links found |

## Notes

- This skill validates links that exist in the **local content directory** only.
  It cannot validate external links (non-aspose.org URLs).
- Locale variant files (`/ar/`, `/fr/`, etc.) are included in the slug index — a link
  to a locale page will resolve correctly if the locale file exists.
- Fragment anchors (`#section-name`) and query parameters are stripped before validation.
