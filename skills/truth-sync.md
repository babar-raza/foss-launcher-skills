---
name: truth-sync
id: S-30
description: >
  Import external knowledge artifacts into the local knowledge directory
  as a validated copy. Schema validation only, no modification.
args: "{family} {platform} {source-path}"
---

# S-30: Truth Sync — Import External Knowledge Artifacts

**Arguments**: $ARGUMENTS
Expected format: `{family} {platform} {source-path}`

## Purpose
Import pre-existing knowledge artifacts from an external directory into `knowledge/{family}/{platform}/external/` as a validated copy. No modification — schema validation only. This skill is **optional**; the pipeline works with scout-only knowledge.

## Pre-conditions
1. The directory at `{source-path}` must exist and be readable
2. Source must contain at minimum: `model.yaml`, `claims.json`

## Steps

1. **Validate source**: Check that `{source-path}` is a valid directory
2. **Validate schema**: Check that `model.yaml` is valid YAML with required fields (`family`, `platform`)
3. **Create target**: `mkdir -p knowledge/{family}/{platform}/external/`
4. **Copy artifacts**: Copy all files from source to target:
   - `model.yaml`
   - `claims.json`
   - `api_surface.json`
   - `formats.md`
   - `limitations.md`
   - `install.md`
   - `snippets/` directory (if exists)
5. **Validate copy**: Verify JSON files are parseable, YAML is valid
6. **Tag provenance**: Add `sync_timestamp` and `source_path` to a `_sync_meta.json` file in the target directory

## Post-conditions
- `knowledge/{family}/{platform}/external/` exists with validated copies
- `_sync_meta.json` records sync timestamp and source path
- All JSON/YAML files are parseable

## Error handling
- If source path not found → abort with clear message
- If any file fails validation → skip that file and warn (don't abort entire sync)
