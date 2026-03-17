# S-34: Repo Scout — Extract Truth from FOSS Repository

**Arguments**: $ARGUMENTS
Expected format: `{family} {platform} {repo-path}`

## Purpose
Extract truth directly from a FOSS repository using tree-sitter analysis. Produces knowledge artifacts in `knowledge/{family}/{platform}/scout/` that serve as an independent verification source alongside FOSS-Launcher outputs.

## Pre-conditions
1. Verify the repo path exists and is a git repository (`git -C {repo-path} rev-parse HEAD`)
2. Verify `scripts/scout.py` exists
3. Verify tree-sitter dependencies are installed: `python -c "import tree_sitter; import tree_sitter_language_pack"`

## Steps

1. **Parse arguments**: Extract `{family}`, `{platform}`, and `{repo-path}` from $ARGUMENTS
2. **Run extraction**: Execute `python scripts/scout.py {family} {platform} {repo-path} knowledge/{family}/{platform}/scout/`
3. **Validate outputs**: Verify the following files were created:
   - `knowledge/{family}/{platform}/scout/model.yaml` — must contain `family`, `platform`, `repo_sha`
   - `knowledge/{family}/{platform}/scout/api_surface.json` — must be valid JSON with at least 1 class
   - `knowledge/{family}/{platform}/scout/claims.json` — must be valid JSON array
   - `knowledge/{family}/{platform}/scout/formats.json` — must exist
   - `knowledge/{family}/{platform}/scout/class_graph.json` — must exist
   - `knowledge/{family}/{platform}/scout/coverage_matrix.json` — must exist
4. **Report**: Print summary of extracted classes, methods, claims, and formats

## Post-conditions
- All output files exist and contain valid data
- `model.yaml` has `source: scout` and a valid `repo_sha`
- No empty arrays in `api_surface.json` (at least 1 class should be found)

## Error handling
- If tree-sitter is not installed, print install instructions: `pip install tree-sitter tree-sitter-language-pack tree-sitter-c-sharp`
- If the repo path doesn't exist, abort with clear message
- If extraction finds 0 classes, warn but don't fail (repo may have unusual structure)
