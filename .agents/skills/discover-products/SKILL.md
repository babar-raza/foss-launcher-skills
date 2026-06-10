---
name: discover-products
id: S-39
description: >
  Scan configured GitHub organizations to discover available FOSS product
  repositories. Outputs a manifest of family/platform/repo_url entries and
  optionally clones repos for immediate scouting.
args: "[{org}] [--clone]"
---

# S-39: Discover Products — GitHub Org Scanner

**Arguments**: $ARGUMENTS
Expected format: `[{org}] [--clone]`
Examples:
- `discover-products` — scan all configured orgs
- `discover-products aspose-cells-foss` — single org
- `discover-products --clone` — scan all orgs and clone repos

## Purpose

Scan the GitHub organizations listed in `configs/intake_config.yaml` using the GitHub REST API to discover all active public FOSS repositories. Extracts `{family}` and `{platform}` from each repo name so discovered products can be immediately handed off to `/repo-scout` or `/launch-product`.

## Pre-conditions

1. Verify `scripts/discover.py` exists
2. Verify `configs/intake_config.yaml` exists
3. Verify `requests` is installed: `python -c "import requests"`
4. (Optional but recommended) Set `$GITHUB_TOKEN` for 5000 req/hr rate limit vs 60 unauthenticated

## Steps

### 1. Parse arguments

- If an org name is provided (e.g. `aspose-cells-foss`) → pass `--org {org}` to the script
- If `--clone` is present → pass `--clone-dir repos/` to the script
- Otherwise → scan all orgs

### 2. Run discovery

```
python scripts/discover.py [--org {org}] [--clone-dir repos/] --output discovered.json
```

### 3. Parse the manifest

Read `discovered.json` (or stdout if `--output` not used). Each entry has:
- `family` — product family key (e.g. `"cells"`)
- `platform` — platform key (e.g. `"python"`)
- `repo_url` — GitHub HTTPS URL
- `full_name` — `"{org}/{repo}"` (e.g. `"aspose-cells-foss/Aspose.Cells-FOSS-for-Python"`)
- `clone_dir` — local path if cloned (only present when `--clone-dir` was passed)
- `cloned` — `true` if newly cloned this run, `false` if already existed

### 4. Present results

Print a table of discovered products:

```
FAMILY       PLATFORM     REPO
------------------------------------------------------------
cells        python       https://github.com/aspose-cells-foss/Aspose.Cells-FOSS-for-Python
3d           dotnet       https://github.com/aspose-3d-foss/Aspose.3D-FOSS-for-.NET
...
```

Report:
- Total repos discovered
- Repos with unresolved platform (`platform == null`) — these may need manual `--org` override
- If `--clone` was passed: how many new clones vs already-present

### 5. Suggest next steps

For each entry where `clone_dir` is set (i.e. cloning was requested):

```
/repo-scout {family} {platform} {clone_dir}
```

Or to run the full pipeline:

```
/launch-product {family} {platform} {clone_dir}
```

If cloning was NOT requested, instruct the user to:
1. Clone the desired repo: `git clone {repo_url} repos/{full_name}`
2. Then: `/repo-scout {family} {platform} repos/{full_name}`

## Post-conditions

- `discovered.json` exists with all discovered repo entries
- Each entry has `family` and `platform` resolved (or flagged as `null` if auto-detection failed)
- If `--clone` was passed: all repos are present under `repos/{full_name}/`

## Error handling

- If `configs/intake_config.yaml` is missing → abort with install instructions: `run install.sh first`
- If `requests` is not installed → abort: `pip install requests`
- If GitHub API returns 404 for an org → warn and continue with remaining orgs
- If rate limited and cannot auto-wait → abort with: "Set $GITHUB_TOKEN to increase rate limit to 5000 req/hr"
- If `family` or `platform` is `null` for a repo → log as WARNING, include in manifest; user can pass the repo explicitly to `/repo-scout`
