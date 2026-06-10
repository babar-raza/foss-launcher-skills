# S-12: Knowledge Diff — Detect Upstream Changes

**Arguments**: $ARGUMENTS
Expected format: `{family} {platform} {repo-path}`

## Purpose
Detect changes in the upstream FOSS repository since the last knowledge extraction by comparing git SHAs and file diffs.

## Pre-conditions
1. `knowledge/{family}/{platform}/merged/model.yaml` must exist with `repo_sha`
2. The repo at `{repo-path}` must be a git repository

## Steps

1. **Get current SHA**: `git -C {repo-path} rev-parse HEAD`
2. **Get stored SHA**: Read `repo_sha` from `model.yaml`
3. **Compare**: If SHAs match, report "no changes" and exit
4. **Get diff**: `git -C {repo-path} diff {stored-sha}..{current-sha} --stat`
5. **Analyze changed files**:
   - Source files (.py, .cs, .java, .ts, .js, .cpp, .h) → API surface may have changed
   - Test files → examples may have changed
   - Manifest files (pyproject.toml, package.json, .csproj) → version/deps may have changed
   - README → descriptions may have changed
6. **Classify impact**:
   - HIGH: Source files in package root changed → re-scout needed
   - MEDIUM: Test/example files changed → snippets may need update
   - LOW: Only docs/config changed → cosmetic
7. **Report**: Write diff report with recommendations

## Output
```
# Knowledge Diff: {family}/{platform}
Stored SHA: {old_sha}
Current SHA: {new_sha}
Impact: HIGH|MEDIUM|LOW

## Changed files
- src/scene.py (source) → HIGH impact
- tests/test_load.py (test) → MEDIUM impact

## Recommendation
Re-run `/repo-scout {family} {platform} {repo-path}` to update knowledge
```

## Post-conditions
- Diff report is printed to output
- If HIGH impact, recommend re-scouting
