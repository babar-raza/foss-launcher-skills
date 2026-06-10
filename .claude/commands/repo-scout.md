# S-34: Repo Scout — Extract Truth from FOSS Repository

**Arguments**: $ARGUMENTS
Expected format: `{family} {platform} [{repo-path}]`
`{repo-path}` is **optional**. When omitted the skill auto-installs the pip package.

## Purpose
Extract truth directly from a FOSS package using tree-sitter analysis. Produces knowledge
artifacts in `knowledge/{family}/{platform}/scout/` that serve as an independent verification
source alongside FOSS-Launcher outputs.

## Repo-path resolution

**With `{repo-path}` supplied** — use it directly (source repo clone with test directories).
Snippets will be extracted from `tests/`, `examples/`, `samples/` inside the repo.

**Without `{repo-path}`** — auto-install the pip package:
```
pip_pkg  = aspose-{family}-foss
temp_dir = /tmp/aspose-{family}-foss-pkg
pip install {pip_pkg} --target {temp_dir}
repo_path = {temp_dir}/aspose/{family}_foss
```
If `{temp_dir}/aspose/{family}_foss` does not exist, use the first subdirectory under
`{temp_dir}/aspose/` as `repo_path`. This is the canonical path for environments
where source repos are not cloned.

> **Snippet limitation (pip-install mode):** Installed packages contain no test directories.
> `scout.py` will write `snippets_index.json` as `[]` and `snippet_count: 0` in `model.yaml`.
> `merge.py` will promote 0 scout snippets (FL snippets still promoted if available).
> To obtain real snippets, run with a cloned source repo that includes `tests/` or `examples/`.

## Pre-conditions

1. **Repo path exists** — if `{repo-path}` was supplied, verify it exists:
   ```
   ls {repo-path}
   ```
   If it doesn't exist, abort with a clear message. Skip this check in pip-install mode.

2. **Verify `scripts/scout.py` exists**:
   ```
   ls scripts/scout.py
   ```

3. **Verify tree-sitter is importable** — first check the user site-packages:
   ```
   USER_SITE=$(python -m site --user-site 2>/dev/null || python -m site --user-site)
   PYTHONPATH="$USER_SITE" python -c "import tree_sitter; import tree_sitter_language_pack"
   ```
   If that fails, install:
   ```
   pip install tree-sitter tree-sitter-language-pack --user
   ```
   Re-verify after install. If still failing, abort with:
   `tree-sitter not available — run: pip install tree-sitter tree-sitter-language-pack --user`

## Steps

1. **Parse arguments** from $ARGUMENTS:
   - If 3 tokens: `family`, `platform`, `repo_path` (explicit source repo)
   - If 2 tokens: `family`, `platform` → resolve `repo_path` via pip-install (see above)

2. **Resolve PYTHONPATH**:
   ```
   USER_SITE=$(python -m site --user-site)
   ```
   Prepend to all subsequent `python` invocations as `PYTHONPATH="$USER_SITE"`.

3. **Run extraction**:
   ```
   PYTHONPATH="$USER_SITE" python scripts/scout.py \
     {family} {platform} {repo_path} knowledge/{family}/{platform}/scout/
   ```

4. **Validate outputs** — verify these files were created:
   - `knowledge/{family}/{platform}/scout/model.yaml` — must contain `family`, `platform`, `source: scout`
   - `knowledge/{family}/{platform}/scout/api_surface.json` — valid JSON, at least 1 class
   - `knowledge/{family}/{platform}/scout/claims.json` — valid JSON array
   - `knowledge/{family}/{platform}/scout/formats.json` — exists
   - `knowledge/{family}/{platform}/scout/class_graph.json` — exists
   - `knowledge/{family}/{platform}/scout/coverage_matrix.json` — exists
   - `knowledge/{family}/{platform}/scout/snippets/snippets_index.json` — exists (may be `[]` in pip mode)

5. **Report** — print summary:
   ```
   family/platform: {class_count} classes, {method_count} methods, {snippet_count} snippets
   repo_sha: {repo_sha or "(pip-installed, no sha)"}
   output: knowledge/{family}/{platform}/scout/
   ```

## Post-conditions
- All output files listed in Step 4 exist and contain valid data
- `model.yaml` has `source: scout`
- `repo_sha` may be empty when running in pip-install mode — this is expected and not an error
- `snippet_count: 0` is expected in pip-install mode — not an error

## Snippet extraction behaviour

| Mode | Snippets | Reason |
|------|----------|--------|
| Source repo clone (with `tests/`) | >0 (if tests exist) | tree-sitter extracts test functions |
| pip-install (no `{repo-path}`) | 0 | No test directories in installed package |

After a pip-install scout run, if `.py` snippet files already exist in `scout/snippets/`
from a previous source-repo run, they are preserved. Run `rebuild_snippet_index.py` to
re-index them:
```
python scripts/maintenance/rebuild_snippet_index.py {family} {platform}
```

## Error handling
- `{repo-path}` not found → abort: `Repo path not found: {repo-path}`
- pip install fails → abort with pip error output
- tree-sitter not installable → abort: `tree-sitter unavailable — see Pre-condition 3`
- 0 classes found → warn but continue: `WARN: 0 classes extracted — verify repo_path points to package root`
