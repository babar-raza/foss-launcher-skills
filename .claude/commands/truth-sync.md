# S-30: Truth Sync — Import External Knowledge into fl/

**Arguments**: $ARGUMENTS
Expected format: `{family} {platform}`

## Purpose
Import external knowledge artifacts into `knowledge/{family}/{platform}/fl/` as a validated copy. No modification — schema validation only. The `fl/` layer is optional — if no external source is available the step is skipped gracefully and the pipeline continues with scout-only knowledge.

## Pre-conditions
1. **External knowledge source** (optional — skip gracefully if absent):
   - Environment variable `EXTERNAL_KNOWLEDGE_PATH` + `/knowledge/{family}/{platform}/`
2. If source not found → print `SKIP: no external knowledge source found` and exit 0 (not an error)
3. If source found → it must contain at minimum: `model.yaml`, `claims.json`

## Steps

1. **Locate source**: Check `$EXTERNAL_KNOWLEDGE_PATH/knowledge/{family}/{platform}/`; skip if absent
2. **Validate source**: Check that `model.yaml` is valid YAML with required fields (`family`, `platform`)
3. **Create target**: `mkdir -p knowledge/{family}/{platform}/fl/`
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
- `knowledge/{family}/{platform}/fl/` exists with validated copies (if source was found)
- `_sync_meta.json` records sync timestamp and source path
- All JSON/YAML files are parseable
- If no source was found: exit 0, no fl/ directory created — downstream steps handle fl/ absence gracefully

## Output artifacts
| File | Purpose |
|------|---------|
| `fl/model.yaml` | External knowledge metadata (claims count, tier, staleness) |
| `fl/claims.json` | LLM-extracted claims with confidence scores |
| `fl/api_surface.json` | External API surface (typed methods, properties) |
| `fl/formats.md` | Format support as extracted externally |
| `fl/limitations.md` | Stub/unimplemented methods identified externally |
| `fl/install.md` | Installation recipe |
| `fl/_sync_meta.json` | Provenance: sync timestamp, source path |

## Error handling
- If source not found → `SKIP` (exit 0, not failure)
- If any file fails validation → skip that file and warn (don't abort entire sync)
- Set `EXTERNAL_KNOWLEDGE_PATH` env var to point to an external knowledge directory to enable enrichment

## When to run
Run this skill when external LLM-extracted knowledge is available and you want to enrich the scout-only knowledge. Without this step the pipeline produces `source: "scout_only"` merged knowledge, which is fully functional.
