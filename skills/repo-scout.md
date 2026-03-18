---
name: repo-scout
id: S-34
description: >
  Extract truth from a FOSS repository using tree-sitter analysis. Produces
  knowledge artifacts in scout/ for independent verification.
args: "{repo-path}"
---

# S-34: Repo Scout — Extract Truth from FOSS Repository

**Arguments**: $ARGUMENTS
Expected format: `{repo-path}` — a GitHub URL (e.g. `https://github.com/org/repo`) or a local directory path

## Purpose
Extract truth directly from a FOSS repository using tree-sitter analysis. Produces knowledge artifacts in `knowledge/{family}/{platform}/scout/` that serve as the primary knowledge source for the content pipeline.

## Pre-conditions
1. Verify `scripts/scout.py` exists
2. Verify tree-sitter dependencies are installed: `python -c "import tree_sitter; import tree_sitter_language_pack"`

## Steps

### 1. Resolve repo path

If `{repo-path}` starts with `https://` or `git@` (it is a URL):

a. **Get remote HEAD SHA**:
   ```
   git ls-remote {repo-path} HEAD | awk '{print $1}'
   ```
   Store the resulting 40-hex SHA as `{remote_sha}`. If this command fails (network error, auth, bad URL), abort with the error output before attempting any clone.

b. **Parse clone destination**: Extract `{org}` and `{repo-name}` from the URL path; set `{clone_dir}` = `repos/{org}/{repo-name}`

c. **Ensure `repos/` is gitignored**: If `.gitignore` in the working directory does not contain `repos/`, append it.

d. **Check SHA cache**:
   - If `{clone_dir}` exists but is not a valid git repo (`git -C {clone_dir} rev-parse HEAD` fails) → treat as corrupt; delete `{clone_dir}` and re-clone
   - Else if `{clone_dir}` exists and `{clone_dir}/.clone_sha` contains `{remote_sha}` → **cache hit**: reuse, set `{local-path}` = `{clone_dir}`, skip to step 2
   - Else if `{clone_dir}` exists and is a valid git repo but `{clone_dir}/.clone_sha` is missing or stale (another tool may have cloned without SHA tracking):
     - Get local HEAD: `git -C {clone_dir} rev-parse HEAD`
     - If local HEAD equals `{remote_sha}` → write `{remote_sha}` to `{clone_dir}/.clone_sha`, treat as **cache hit**, skip to step 2
     - Else → delete `{clone_dir}` and re-clone (see below)
   - Otherwise (dir does not exist → **cache miss**) → clone:
     ```
     git clone --depth=1 {repo-path} {clone_dir}
     ```
   - Write `{remote_sha}` to `{clone_dir}/.clone_sha`
   - Set `{local-path}` = `{clone_dir}`

If `{repo-path}` is a local directory path: set `{local-path}` = `{repo-path}` (no clone step).

### 2. Pre-conditions check
- Verify `{local-path}` is a git repository: `git -C {local-path} rev-parse HEAD`
- Verify `scripts/scout.py` exists

### 3. Auto-detect family and platform

Derive `{family}` and `{platform}` from the repo URL or local path name:

**Family** — from the GitHub org name or parent directory name:
- Strip `aspose-` prefix and `-foss` suffix: `aspose-cells-foss` → `cells`
- Known families: `cells`, `note`, `3d`, `words`, `pdf`, `slides`, `barcode`, `cad`, `diagram`, `drawing`, `email`, `finance`, `font`, `gis`, `html`, `imaging`, `medical`, `ocr`, `omr`, `page`, `psd`, `pub`, `svg`, `tasks`, `tex`, `zip`

**Platform** — from the repo name (try in order):
1. Pattern `*-for-{platform}` → e.g. `aspose-cells-for-python` → `python`
2. Last hyphen-segment if it matches a known platform → e.g. `aspose-cells-python` → `python`
3. Fallback: scan dominant file extension in `{local-path}` (`.py`→`python`, `.cs`→`dotnet`, `.java`→`java`, `.ts`→`typescript`, `.js`→`javascript`, `.cpp`/`.h`→`cpp`)

Known platforms: `python`, `dotnet`, `java`, `cpp`, `typescript`, `javascript`, `nodejs`

If either cannot be determined, abort with:
> "Could not determine {family/platform} from repo name. Rename repo to `aspose-{family}-for-{platform}` or use a local path under `knowledge/{family}/{platform}/`."

### 4. Run extraction
```
python scripts/scout.py {family} {platform} {local-path} knowledge/{family}/{platform}/scout/
```

### 5. Validate outputs
Verify the following files were created:
- `knowledge/{family}/{platform}/scout/model.yaml` — must contain `family`, `platform`, `repo_sha`
- `knowledge/{family}/{platform}/scout/api_surface.json` — must be valid JSON with at least 1 class
- `knowledge/{family}/{platform}/scout/claims.json` — must be valid JSON array
- `knowledge/{family}/{platform}/scout/formats.json` — must exist
- `knowledge/{family}/{platform}/scout/class_graph.json` — must exist
- `knowledge/{family}/{platform}/scout/coverage_matrix.json` — must exist

### 6. Report
Print summary including:
- Clone status: `cache hit (sha={remote_sha})` or `fresh clone (sha={remote_sha})` (URL input only)
- Extracted classes, methods, claims, and formats counts

## Post-conditions
- All output files exist and contain valid data
- `model.yaml` has `source: scout` and a valid `repo_sha`
- No empty arrays in `api_surface.json` (at least 1 class should be found)

## Error handling
- If tree-sitter is not installed, print install instructions: `pip install tree-sitter tree-sitter-language-pack tree-sitter-c-sharp`
- If `git ls-remote` fails (network, auth, bad URL), abort before cloning: print the git error and stop
- If clone fails, abort with the git error output
- If `{clone_dir}` exists but is not a valid git repo (corrupt/partial), delete it and re-clone
- If the repo path doesn't exist (local path), abort with clear message
- If extraction finds 0 classes, warn but don't fail (repo may have unusual structure)

## Verification

Run these to validate each branch of the clone cache logic:

1. **Fresh clone**: `rm -rf repos/aspose-cells-foss/aspose-cells-python && /repo-scout https://github.com/aspose-cells-foss/aspose-cells-python`
   - Expect: clone to `repos/aspose-cells-foss/aspose-cells-python/`, `.clone_sha` written, `fresh clone (sha=...)` in report, artifacts in `knowledge/cells/python/scout/`
2. **Cache hit**: Run same command again without deleting the repo
   - Expect: `cache hit (sha=...)`, no git clone output, same artifacts
3. **SHA mismatch (upstream changed)**: Overwrite `repos/aspose-cells-foss/aspose-cells-python/.clone_sha` with `0000000000000000000000000000000000000000` then re-run
   - Expect: re-clone triggered, `.clone_sha` updated to real SHA
4. **Corrupt clone**: `rm repos/aspose-cells-foss/aspose-cells-python/.git -rf` then re-run
   - Expect: dir deleted and re-cloned
5. **Pre-existing clone without SHA (discover-products interop)**: Remove only `.clone_sha`: `rm repos/aspose-cells-foss/aspose-cells-python/.clone_sha` then re-run
   - Expect: local HEAD checked against remote; if match → `.clone_sha` written, no re-clone; if mismatch → re-clone
6. **Local path**: `/repo-scout repos/aspose-cells-foss/aspose-cells-python`
   - Expect: no clone step, auto-detect `cells`/`python`, produce artifacts
7. **Bad URL**: `/repo-scout https://github.com/does-not-exist/no-such-repo`
   - Expect: abort after `git ls-remote` failure with error message
