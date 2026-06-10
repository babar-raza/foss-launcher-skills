# S-105: Section Enhance -- Generic Repo-Grounded Section Enhancer

<!-- CONTRACT: agent-executed
     purpose: inspect a target content section, detect gaps against clone-cache and knowledge truth, produce read-only proposal pack
     preconditions: target section exists under $CONTENT_REPO_PATH/content/; knowledge preferred; clone cache preferred
     postcondition: reports/section-enhance/{section-slug}/ written with up to 10-file proposal pack
     idempotent: yes -- same inputs and clone cache SHA produce same gap detection results
     verified: 2026-04-27 (ported from aspose S-96)
-->

**Arguments**: $ARGUMENTS
Expected format: `{target} [--mode audit|draft] [--scope section|page] [--family {family}] [--platform {platform}] [--clone-cache {path}] [--no-llm] [--out {output-dir}]`

> **Standalone mode note**: In foss-launcher standalone mode, `content/` and `knowledge/` are
> accessed via `CONTENT_REPO_PATH` environment variable. Set this before invoking:
> `export CONTENT_REPO_PATH=/path/to/your/content-repo`

## Purpose

Inspect any content section in the target repository and produce a read-only proposal pack
identifying gaps and suggesting improvements grounded in clone-cache truth and knowledge artifacts.
Phase 1 is proposal-only: zero writes to `content/`.

## Pre-conditions

1. `CONTENT_REPO_PATH` set to the content repository root
2. Target section exists under `$CONTENT_REPO_PATH/content/`
3. Knowledge artifacts at `$CONTENT_REPO_PATH/knowledge/{family}/{platform}/merged/` preferred
4. Clone cache at `$CONTENT_REPO_PATH/runs/.clone_cache/aspose_{family}_{platform}/` preferred
5. Clone cache path must NOT contain `foss-launcher` or `foss_launcher` anywhere in the resolved path
6. Output goes to `reports/section-enhance/{section-slug}/` (gitignored; local only)

## Steps

### Step 1: Parse arguments and classify target (SP-0 + SP-1)

Parse `{target}` from $ARGUMENTS. Apply path resolution:

1. Strip any protocol prefix (`https://`)
2. Apply alias corrections for known path variants (record in run manifest)
3. Classify target by subdomain, family, platform, section_type, depth
4. Validate resolved canonical path exists under `$CONTENT_REPO_PATH/content/`
5. Determine clone candidates at `$CONTENT_REPO_PATH/runs/.clone_cache/`

Record in `reports/section-enhance/{section-slug}/00-run-manifest.json`.

### Step 2: Section inventory (SP-2)

Glob all `.md` files under the resolved canonical path (max 3 levels deep).
Classify each as: index, leaf, structural, orphan, or flagged-invalid-filename.
Write `reports/section-enhance/{section-slug}/01-section-inventory.md`.

### Step 3: Activate truth adapters (SP-3)

Based on SP-0 classification, activate applicable adapters:
- Adapter A (Docs): `api_surface.json`, `claims.json`, `snippets/`
- Adapter B (Products): `claims.json`, clone README
- Adapter C (KB): `api_surface.json`, `claims.json`, `snippets/`
- Adapter D (Blog): `claims.json` (narrative), README
- Adapter E (Reference): `api_surface.json` exclusively
- Adapter F (Clone-Cache): clone README, package metadata, targeted source greps
- Adapter G (Sibling-Content): existing sibling pages
- Adapter H (Package-Metadata): setup.py, pyproject.toml, pom.xml, etc.

### Step 4: Extract metadata and shortcode patterns (SP-4)

Read 5+ nearest sibling/parent pages to classify frontmatter fields as Required/Common/Optional.
Record in `metadata_pattern.json` and `shortcode_pattern.json`.

### Step 5: Build clone-cache mental model (SP-5)

1. Verify clone cache root does not contain `foss-launcher`
2. For each clone candidate: read README, package metadata, targeted API name greps
3. Write `reports/section-enhance/{section-slug}/02-clone-cache-truth-map.md`

### Step 6: Load knowledge artifacts (SP-6)

Load `api_surface.json`, `claims.json`, `formats.json`, `limitations.md`, `snippets/` listing.
Write `reports/section-enhance/{section-slug}/06-evidence-map.json`.

### Step 7: Detect gaps (SP-7)

Check: missing index, missing child pages, missing code examples, missing FAQ/conclusion,
inconsistent metadata, invalid filenames, duplicate topics, placeholder content,
outdated terminology, unsupported API claims, orphan pages.

Write `reports/section-enhance/{section-slug}/03-gap-report.md` and `03-gap-report.json`.

### Step 8: Rank candidates (SP-8)

Score each gap by: severity x evidence strength x fix type.
Assign confidence per evidence tier (Strong >=0.85 / Medium-high 0.70-0.84 / Medium 0.60-0.69 / Weak 0.40-0.59).
Write `reports/section-enhance/{section-slug}/04-candidate-list.md`.

### Step 9: Generate proposals (SP-9)

For each candidate with confidence >= 0.40 generate: new-page, section-addition, or metadata-fix proposals.
All proposals include governance-mandatory `provenance:` and `evidence:` blocks.
Write one file per proposal under `reports/section-enhance/{section-slug}/05-proposals/`.

### Step 10: Run verification gates (SP-10)

Gates: stale-path, filename regex, slug regex, metadata fields, shortcode names, evidence,
API name, link validity, conflict, auto-updatable flag.
Remove or demote any proposal that fails a gate.
Write `reports/section-enhance/{section-slug}/08-verification-checklist.md`.

### Step 11: Write supporting artifacts

- `07-risk-report.md` -- risks per proposal
- `09-handoff-notes.md` -- downstream skill invocations (human approval mandatory)

**Handoff downstream skills** (human approval mandatory before any write):
- docs new page: `/new-docs-page` (S-51)
- kb how-to: `/new-kb-howto` (S-53)
- kb faq: `/new-kb-faq` (S-54)
- reference: `/new-reference-page` (S-55)
- blog: `/new-blog-post` (S-52)
- products: `/new-products-page` (S-66)
- section addition: `/manual-edit` (S-78) with proposal as specification
- After all writes: `/content-check` (S-50) -> `/eval-page` (S-25) -> `/commit` (S-81)

### Step 12: Report

```
SECTION ENHANCE -- {canonical_path}
Mode: {audit|draft}
Section type: {section_type}
Clone: {found|missing|ambiguous}
Knowledge: {current|stale since {date}|absent}

Section inventory: {N} pages ({index_count} index, {leaf_count} leaf, {flagged_count} flagged)
Gap detection: {N} gaps found ({high_count} high, {medium_count} medium, {low_count} low)
Proposals: {N} generated

Output: reports/section-enhance/{section-slug}/
Next step: human reviews and approves proposals; invoke downstream skills per 09-handoff-notes.md
```

## Post-conditions

- `reports/section-enhance/{section-slug}/` written with all artifact files
- Zero files written under `content/`
- All proposals pass SP-10 verification gates

## Error handling

| Error | Cause | Fix |
|---|---|---|
| Path not found | Input target does not match any known content path | Check CONTENT_REPO_PATH; verify path exists |
| STALE_CLONE_CACHE_PATH | Clone cache path contains `foss-launcher` | Check CONTENT_REPO_PATH; use default cache location |
| Clone missing | Clone cache directory does not exist | Run `/knowledge-update {family} {platform}` |
| Knowledge absent | `knowledge/` directory missing | Run `/knowledge-update {family} {platform}` |
| Knowledge stale | stale_since not null | Run `/knowledge-diff` then `/knowledge-update` |

## Related skills

- S-21 `/page-enhance` -- single-page enhancer
- S-62 `/gap-eval` -- verifies existing content claims against clone cache
- S-63 `/gap-plan` -- generates fix specs from gap-eval findings
- S-12 `/knowledge-diff` -- detects knowledge staleness
- S-14 `/knowledge-update` -- refreshes knowledge artifacts
