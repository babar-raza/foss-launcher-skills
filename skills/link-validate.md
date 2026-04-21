---
name: link-validate
id: S-70
description: >
  Validate cross-subdomain internal links in content files. Reports BROKEN links
  where the target slug does not exist in the local content directory.
  Use before publishing to catch stale cross-site links.
args: "{family} {platform} | all | --files file1.md ..."
---

# S-70: Link Validate — Cross-Subdomain Link Validation

**Arguments**: $ARGUMENTS
Expected format: `{family} {platform}` | `all` | `--files file1.md ...`

## Purpose

Validate cross-subdomain internal links in content files. Finds links pointing to
other aspose.org subdomains (docs → kb, blog → docs, etc.) and reports BROKEN links
where the target slug does not exist in the local content directory.

Use before publishing to catch stale cross-site links that would result in 404s on production.

## Pre-conditions

`$CONTENT_REPO_PATH` configured; content files exist under `$CONTENT_REPO_PATH/content/`.

## Steps

1. **Run validation** for the target scope:

   ```bash
   # One product:
   python scripts/pipeline/link_validator.py {family} {platform}

   # Specific files:
   python scripts/pipeline/link_validator.py --files path/to/file.md

   # All content:
   python scripts/pipeline/link_validator.py all
   ```

2. **Review BROKEN findings**. Each BROKEN finding shows:
   - Source file containing the broken link
   - Full URL of the broken link
   - Target subdomain and path that was not found

3. **Fix or accept each finding**:
   - **Update the URL** if the target page exists at a different path
   - **Remove the link** if the target page no longer exists
   - **Create the missing page** using appropriate generation skill
   - **Accept as expected** if the target will be created shortly — document in your PR

4. **JSON output for CI integration**:
   ```bash
   python scripts/pipeline/link_validator.py {family} {platform} --json \
     > reports/link-validation/{family}-{platform}-{timestamp}.json
   ```

## Post-conditions

- BROKEN links are documented or fixed
- Report saved to `reports/link-validation/`
- No new BROKEN cross-subdomain links remain in modified content files

## Exit codes

| Code | Meaning |
|------|---------|
| 0 | No broken links found |
| 1 | One or more broken links found |

## Notes

- Validates links in the **local content directory** only — cannot validate external URLs
- Locale variant files are included in the slug index
- Fragment anchors (`#section-name`) and query parameters are stripped before validation
