---
name: link-validate
id: S-65
description: >
  Validate cross-subdomain internal links in content files; report BROKEN links where the target slug does not exist locally
args: "{family} {platform} | all | --files file1.md ..."
---

> Cross-skill references like `/knowledge-bootstrap` refer to sibling skills in this directory.

# S-65: Link Validate — Cross-Subdomain Link Validation

**Arguments**: $ARGUMENTS

## Purpose

Find and report broken internal links across aspose.org subdomains (docs → kb, blog → docs, etc.).
Use before publishing to catch stale cross-site links.

## Pre-conditions

None. Works from local content directory only.

## Steps

```bash
# One product
python scripts/pipeline/link_validator.py {family} {platform}

# Specific files
python scripts/pipeline/link_validator.py --files path/to/file.md

# All content
python scripts/pipeline/link_validator.py all

# JSON output for reporting
python scripts/pipeline/link_validator.py {family} {platform} --json \
  > reports/link-validation/{family}-{platform}-$(date +%Y%m%d).json
```

For each BROKEN finding: update the URL, remove the link, or create the missing page.

## Exit codes
- 0: No broken links
- 1: Broken links found
