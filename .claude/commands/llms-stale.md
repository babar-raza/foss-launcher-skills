# S-120: LLMs Stale -- Detect Stale/Missing LLMs Outputs

**Arguments**: $ARGUMENTS

## Purpose
Compare source `.md` sha256 hashes against a provenance manifest to catch
outputs that are stale (source changed since last generation) or missing
(output `.txt` deleted) without a full regenerate-and-diff.

## Manifest
`{reports_path}/llms-manifest.json` (default `reports/llms-manifest.json`)
-- reuses `config.yaml`'s existing `reports_path`, no new config key.

## Steps

### Check only (for a CI-style gate)
```bash
.venv/bin/python scripts/llms_stale.py --output llms-output --check-only
```
Exit 0 = clean. Exit 1 = stale or missing outputs detected.

### Update the manifest after regeneration
```bash
.venv/bin/python scripts/llms_stale.py --output llms-output --update-manifest
```

### Both in one pass
```bash
.venv/bin/python scripts/llms_stale.py --output llms-output --update-manifest --check-only
```
Reports what was stale **this run** (against the manifest as it stood
before the update), then refreshes the manifest for next time -- it does
not compare the manifest against itself after updating it, which would
trivially always report clean.

## Workflow sequence
1. Source `.md` changes -> `STALE` detected by this skill
2. Run `/llms-generate` -> outputs regenerated
3. Run this skill with `--update-manifest` -> manifest refreshed
4. Run `--check-only` -> exit 0 confirmed

## Related Skills
- `/llms-generate` -- regenerate to fix stale outputs
- `/llms-coverage` -- structural presence
- `/llms-fidelity` -- content quality
