---
name: evidence-cite
id: S-24
description: >
  Attach evidence citations to a content page. For pages with code blocks,
  runs attach_evidence.py (deterministic). For prose-only pages with no API
  tokens, manually maps factual claims to claim_ids from the knowledge model.
args: "{content-file-path}"
---

# S-24: Evidence Cite — Attach Knowledge Citations

**Arguments**: $ARGUMENTS
Expected format: `{content-file-path}`

## Purpose

Write or update the `evidence:` YAML frontmatter block in a content page, linking
it to the backing knowledge model. Citations must be **deterministic and rerunnable**:
the same page + same knowledge model must produce the same evidence block every time.

Do **not** use inline HTML comments (`<!-- evidence: ... -->`).
Do **not** include a `ground_check:` field — it is self-reported and unverifiable.

## Two-path approach

### Path A — Pages with code blocks (automated, ~70% of pages)

Run `attach_evidence.py`. It is deterministic and requires no LLM:

```bash
python scripts/pipeline/commands/content/attach_evidence.py --files {content-file-path}
```

This script:
1. Extracts verified API tokens from code blocks
2. Maps each token → `claim_id` via `api_to_claim` index built from `merged/claims.json`
3. Cross-references format mentions against `merged/formats.json`
4. Writes the result to the page frontmatter

**Do not run this path manually** — just call the script. It skips files with audit FAILs.

### Path B — Prose-only pages (manual, ~30% of pages)

For pages with no code blocks (pure explanatory content), `attach_evidence.py` will write
`claims: []` and `apis: []`. To improve coverage, manually find relevant claim_ids:

1. Read `knowledge/{family}/{platform}/merged/claims.json`
2. For each factual statement in the page, find the best matching `claim_id`
   (match on `text` field; only use claims with `confidence >= 0.7` if the field exists)
3. Add the claim_ids to the `evidence.claims` list

## Frontmatter schema

```yaml
evidence:
  model_sha: "<repo_sha from merged/model.yaml>"   # required — anchors to knowledge version
  model_version: "<version from merged/model.yaml>" # required
  claims:
    - CLM-3d-64ee67      # claim_ids from merged/claims.json (empty list is valid)
    - CLM-3d-abc123
  apis:
    - Scene.open         # ClassName.method verified against merged/api_surface.json
    - Node.add_child_node
  formats:               # omit if page has no format content
    - { ext: glb, support: both }
    - { ext: fbx, support: import }
```

### Field reference

| Field | Required | Description |
|-------|----------|-------------|
| `model_sha` | yes | `repo_sha` from `merged/model.yaml` — staleness is detected by audit.py |
| `model_version` | yes | `version` from `merged/model.yaml` |
| `claims` | yes | List of `claim_id` strings (empty list `[]` is valid for prose pages) |
| `apis` | yes | `ClassName.method` tokens from code blocks (empty list `[]` is valid) |
| `formats` | no | Only when page discusses file format handling |

## Pre-conditions
1. Content file must exist
2. `knowledge/{family}/{platform}/merged/` must exist
3. Run `python scripts/pipeline/commands/content/audit.py --files {path}` first — fix all FAIL findings before attaching evidence

## Post-conditions
- Content file frontmatter contains a valid `evidence:` block
- `model_sha` matches current `knowledge/{family}/{platform}/merged/model.yaml`
- All listed `claim_id` values exist in `merged/claims.json` (when claims.json is populated)
- All listed `api` values exist in `merged/api_surface.json`
- No `<!-- evidence: ... -->` HTML comments remain in the body
- Running `attach_evidence.py` again on the same file with the same model produces identical output

## Staleness handling

When `knowledge/{family}/{platform}/merged/model.yaml` is updated (new product version):
- `audit.py` will emit WARN "Evidence stale: model updated" for all pages with old `model_sha`
- Fix by rerunning: `python scripts/pipeline/commands/content/attach_evidence.py {family} {platform}`
- This is safe to run at any time; pages already current are skipped
