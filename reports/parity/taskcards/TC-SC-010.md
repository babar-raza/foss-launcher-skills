# TC-SC-010: Implement backing script for blog-migrate

**ID**: SC-010
**Title**: Implement backing script for blog-migrate
**Purpose**: Create a working backing script for the blog-migrate skill

## Scope
Port or implement the backing script for blog-migrate in foss-launcher.

## Inputs
- D:/onedrive/Documents/GitHub/aspose.org/skills/blog-migrate.md

## Allowed Changes
- scripts/pipeline/commands/misc/blog_migrate.py

## Forbidden Changes
- skills/
- docs/

## Dependencies
- LB-001

## Implementation Steps
1. Read skills/blog-migrate.md to understand expected behavior
2. Identify all CLI flags and I/O contracts
3. Adapt path handling for CONTENT_REPO_PATH pattern
4. Write backing script with main() and --dry-run support
5. Update skills/registry.yaml to point script: field to new script

## Verification Steps
1. python <script> --help returns usage without error
2. python scripts/validate_skills.py exits 0

## Expected Artifacts
- Script file for blog-migrate
- Updated skills/registry.yaml

**Risk**: MEDIUM — new code, must not break existing tests
**Rollback**: Delete script file; revert registry.yaml script: field to null

## Done Criteria
- [ ] Script file exists and has main()
- [ ] --dry-run mode works without writing to content
- [ ] validate_skills.py passes