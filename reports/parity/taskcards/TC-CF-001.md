# TC-CF-001: Create .env.example with all required env vars

**ID**: CF-001
**Title**: Create .env.example with all required env vars
**Purpose**: Document all environment variables needed by foss-launcher skills

## Scope
Create .env.example at repo root listing all env vars with descriptions.

## Inputs
- AGENTS.md (list of config keys)
- skills/registry.yaml (config_keys fields)
- scripts/ (grep for os.getenv)

## Allowed Changes
- .env.example

## Forbidden Changes
- Any script files
- config.yaml
- AGENTS.md

## Dependencies
- None

## Implementation Steps
1. Run `grep -r 'os.getenv\|os.environ' scripts/ | grep -v '.pyc'` to find all env var references
2. Identify all unique env var names
3. Write .env.example with each var, a description, and example value
4. Add comment block explaining CONTENT_REPO_PATH is required for content-writing skills

## Verification Steps
1. Verify .env.example parses as valid shell comments + assignments
2. Verify all env vars referenced in scripts/ appear in .env.example

## Expected Artifacts
- .env.example at repo root

**Risk**: LOW — documentation only, no code changes
**Rollback**: Delete .env.example if introduced incorrectly

## Done Criteria
- [ ] .env.example exists at repo root
- [ ] All env vars from scripts/ are documented