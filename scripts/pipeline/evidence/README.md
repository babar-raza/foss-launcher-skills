# evidence/ — Evidence Frontmatter Generation

Builds the `evidence:` frontmatter block in content pages by mapping verified API tokens and format references to structured claim IDs from the knowledge model. Fully deterministic — same inputs always produce the same output. No LLM required.

Called by the `commands/healing/attach_evidence.py` CLI entry point.

## CLI Usage

All commands must be run from the repo root.

```bash
# One product
python scripts/pipeline/commands/healing/attach_evidence.py 3d python

# All products
python scripts/pipeline/commands/healing/attach_evidence.py all

# Specific files
python scripts/pipeline/commands/healing/attach_evidence.py --files content/docs.aspose.org/en/3d/python/index.md

# Preview without writing
python scripts/pipeline/commands/healing/attach_evidence.py 3d python --dry-run

# Force re-attach even if model_sha is current
python scripts/pipeline/commands/healing/attach_evidence.py 3d python --force

# Auto-refresh knowledge before attaching
python scripts/pipeline/commands/healing/attach_evidence.py 3d python --auto-refresh
```

## Modules

### runner.py — Evidence Attachment Orchestration

Provides `attach_evidence()`, `attach_product()`, `attach_files()`, and `main()`.

**`attach_evidence(filepath, knowledge, dry_run=False, force=False) -> str`**

Builds and writes the evidence block for a single file. Returns a status string: `UPDATED`, `SKIP (current)`, `SKIP (audit FAILs)`, `DRY-RUN`, or `ERROR`.

Rules:
- Pages with audit FAIL findings are skipped — evidence only attests verified content
- Pages where `evidence.model_sha` already matches the current knowledge SHA are skipped (idempotent), unless `--force`
- Prose-only pages (no code blocks) get an honest `evidence:` block with empty `claims` and `apis`

**`attach_product(family, platform, dry_run=False, force=False) -> dict`**

Attaches evidence to all discovered content files for a product. Returns a counts dict.

**`attach_files(file_paths, dry_run=False, force=False) -> dict`**

Attaches evidence to specific files, inferring product from path.

### mapper.py — Token-to-Evidence Mapping

Maps verified API tokens and format references to claim IDs.

| Function | Description |
|----------|-------------|
| `_map_tokens_to_evidence(tokens, knowledge)` | Returns `(claim_ids, api_refs)` — maps each verified token to its claim_id in knowledge |
| `_detect_formats(filepath, knowledge)` | Scans page text for format references; returns list of format names present |
| `_build_sections_evidence(filepath, knowledge)` | Splits page by H2/H3 headings; returns per-section evidence breakdown |

### sections.py — Markdown Section Parsing

**`_parse_sections(filepath) -> list[dict]`**

Splits a markdown file into sections at H2 (`##`) and H3 (`###`) headings. Each section record has `heading`, `line`, and `content`.

### writer.py — Frontmatter Writer

**`_write_evidence_to_frontmatter(filepath, evidence) -> bool`**

Atomically updates the `evidence:` block in YAML frontmatter. Merges with any existing manual claims rather than replacing them. Returns `True` on success.

## Evidence Block Schema

The following YAML structure is written to each content page's frontmatter:

```yaml
evidence:
  model_sha: "abc123def456"        # repo commit SHA the evidence was built from
  model_version: "1.2.3"           # package version
  claims:                          # claim_ids from claims.json matched to this page
    - "CLM-3d-a1b2c3"
    - "CLM-3d-d4e5f6"
  apis:                            # API class/method references verified in code blocks
    - "Scene"
    - "Scene.open"
  formats:                         # File formats referenced in this page
    - "FBX"
    - "OBJ"
  sections:                        # Per-section breakdown (optional)
    - heading: "Loading a 3D File"
      line: 42
      claims: ["CLM-3d-a1b2c3"]
      apis: ["Scene.open"]
```

The `evidence:` block is **internal-only** — never expose it to end users in rendered output.

## Inputs and Outputs

**Inputs:**
- Content page (markdown with YAML frontmatter)
- `knowledge/{family}/{platform}/merged/api_surface.json`
- `knowledge/{family}/{platform}/merged/claims.json`
- `knowledge/{family}/{platform}/merged/formats.json`
- `knowledge/{family}/{platform}/merged/index.json` (for model_sha)

**Output:**
- Updated `evidence:` block written into content page frontmatter

## Used By

- **S-24 evidence-cite skill**
- Content generation agents (verify evidence before publishing)
