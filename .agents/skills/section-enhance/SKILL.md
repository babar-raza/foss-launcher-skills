---
name: section-enhance
id: S-96
description: >
  Inspect any content section in the aspose.org repository -- regardless of subdomain, family, platform, or section depth -- and produce a read-only proposal pack identifying gaps and suggesting improvements grounded in clone-cache truth and knowledge artifacts.
---

> Cross-skill references like `/knowledge-bootstrap` refer to sibling skills in this directory.

<!-- CONTRACT: agent-executed
     purpose: inspect a target content section, detect gaps against clone-cache and knowledge truth, produce read-only proposal pack
     preconditions: target section exists under content/; knowledge/{family}/{platform}/merged/ preferred; clone cache preferred but not required
     postcondition: reports/section-enhance/{section-slug}/ written with 10-file proposal pack
     idempotent: yes -- same inputs and clone cache SHA produce same gap detection results
     verified: 2026-04-24
-->
# S-96: Section Enhance -- Generic Repo-Grounded Section Enhancer

**Arguments**: $ARGUMENTS
Expected format: `{target} [--mode audit|draft] [--scope section|page] [--family {family}] [--platform {platform}] [--clone-cache {path}] [--no-llm] [--out {output-dir}]`

## Purpose
Inspect any content section in the aspose.org repository -- regardless of subdomain, family, platform, or section depth -- and produce a read-only proposal pack identifying gaps and suggesting improvements grounded in clone-cache truth and knowledge artifacts. Phase 1 is proposal-only: zero writes to `content/`.

## Pre-conditions
1. Target section exists under `content/` (after SP-0/SP-1 path resolution)
2. Knowledge artifacts at `knowledge/{family}/{platform}/merged/` preferred; skill degrades gracefully without them (knowledge-only confidence ceiling applies)
3. Clone cache at `runs/.clone_cache/aspose_{family}_{platform}/` preferred; skill degrades gracefully if absent
4. Clone cache path must NOT contain `foss-launcher` or `foss_launcher` anywhere in the resolved absolute path string <!-- PROHIBITION_OBSOLETE_FOSS_LAUNCHER_REFERENCE -->
5. Output goes to `reports/section-enhance/{section-slug}/` (gitignored; local only)

## Steps

> **Skill context gate** -- run before step 1:
> ```bash
> PYTHONPATH=scripts/pipeline .venv/Scripts/python scripts/pipeline/commands/governance/skill_context.py begin --skill S-96 --scope "*"
> ```

### Step 1: Parse arguments and classify target (SP-0 + SP-1)

Parse `{target}` from $ARGUMENTS. Apply path resolution:

1. Strip any protocol prefix (`https://`)
2. Apply alias lookup table (record every correction in run manifest under `input_aliases`; warn user):

| Input alias | Canonical form | Evidence |
|---|---|---|
| `docs.aspose.net` | `docs.aspose.org` | `configs/docs.aspose.org.toml` baseURL |
| `developers-guide` | `developer-guide` | `content/docs.aspose.org/en/cells/python/` listing |
| Missing `/en/` for docs | Insert `/en/` | `configs/docs.aspose.org.toml` contentDir |
| Missing `/en/` for kb | Insert `/en/` | `content/kb.aspose.org/en/` exists |
| Missing `/en/` for products | Insert `/en/` | `content/products.aspose.org/en/` exists |
| Missing `/en/` for reference | Insert `/en/` | `content/reference.aspose.org/en/` exists |
| blog -- do NOT insert `/en/` | `content/blog.aspose.org/{family}/` | `content/blog.aspose.org/` has no `/en/` level |

3. Classify target:

| Dimension | Possible values |
|---|---|
| `subdomain` | docs, kb, products, blog, reference, unknown |
| `family` | detected from path or `--family` override |
| `platform` | detected from path or `--platform` override; none for family-level targets |
| `section_type` | family-index, platform-index, feature-section, topic-section, post-cluster, namespace-section, structural-index, unknown |
| `depth` | family, platform, section, subsection, page |
| `clone_count` | 0 (no matching clone), 1 (exact match), N (multiple candidates) |

4. Validate resolved canonical path exists under `content/`. If path does not exist after all alias corrections: **HALT** with error message listing corrections attempted. Do not guess further.

5. Determine clone candidates:
   - family + platform both known: single clone `aspose_{family}_{platform}`
   - family known, platform unknown: multiple candidates `aspose_{family}_*` present in cache
   - Neither known: zero clones; knowledge-only mode
   - Multiple families: ambiguous; list all candidates; flag for human review; use knowledge-only mode

Record everything in `reports/section-enhance/{section-slug}/00-run-manifest.json`:
- `input_path`, `canonical_path`, `input_aliases`, `subdomain`, `family`, `platform`, `section_slug`, `section_type`
- `clone_cache_root` (absolute path from `scripts/pipeline/core/clone_cache.py:cache_root()`)
- `clone_cache_contains_foss_launcher: false` (always verified)
- `clone_candidates`, `clone_sha` (HEAD SHA if clone exists)
- `knowledge_stale_since` (from `knowledge/{family}/{platform}/merged/model.yaml`, null if current)
- `run_timestamp`

### Step 2: Section inventory (SP-2)

Glob all `.md` files under the resolved canonical path (max 3 levels deep).

For each file:
- Read frontmatter; extract: title, weight, description, grade, auto_updatable, provenance.last_mechanism, provenance.content_origin, page_role, layout
- Count: words (rough), code blocks, shortcode occurrences (grep for `{{<`)
- Classify as: index, leaf, structural, orphan, or flagged-invalid-filename
- Validate filename against regex `^(_index|index(\.[a-z]{2,3})?|[a-z][a-z0-9-]*)\.md$`
  - Flag filenames starting with `-` as `INVALID_FILENAME`
  - Flag filenames with uppercase characters as `INVALID_FILENAME`
  - Note: `-graph.md` is a known existing violation in the repo -- flag but do not propose new files with this pattern

Write `reports/section-enhance/{section-slug}/01-section-inventory.md`.

### Step 3: Activate truth adapters (SP-2b)

Based on SP-0 classification, activate applicable adapters:

**Adapter A -- Docs**: subdomain=docs. Sources: `api_surface.json`, `claims.json`, `snippets/`, `limitations.md`. Confidence ceiling: 0.90 API existence, 0.70 feature claims. Do NOT use for: product marketing claims, format-only pages.

**Adapter B -- Products**: subdomain=products. Sources: `knowledge/{family}/*/merged/claims.json`, clone README. Confidence ceiling: 0.70. Do NOT use for: API-level detail, platform-specific claims without qualifier.

**Adapter C -- KB**: subdomain=kb. Sources: `api_surface.json`, `claims.json`, `snippets/`. Confidence ceiling: 0.85 API steps, 0.65 prose claims. Do NOT use for: reference-level API enumeration.

**Adapter D -- Blog**: subdomain=blog. Sources: `claims.json` (narrative only), README. Confidence ceiling: 0.60. Do NOT use for: precise API names or method signatures.

**Adapter E -- Reference**: subdomain=reference. Sources: `api_surface.json` exclusively. Confidence ceiling: 0.95 member existence. Do NOT use for: procedural claims, feature narrative.

**Adapter F -- Clone-Cache**: clone exists and path does not contain `foss-launcher`. Sources: clone README, package metadata, targeted source greps for API names from api_surface.json, `samples/`/`examples/`/`tests/` listing. Scoped inspection only: do NOT read all source files; do NOT run any clone scripts. Confidence ceiling: 0.95. Must not be used if `STALE_CLONE_CACHE_PATH` detected.

**Adapter G -- Sibling-Content**: sibling pages exist. Sources: existing content pages in target directory and immediate parent. Confidence ceiling: 0.90 structure/metadata, 0.40 factual claims (sibling content is not ground truth for API existence). Do NOT use for: fact-checking API claims.

**Adapter H -- Package-Metadata**: clone exists. Sources: `setup.py`, `pyproject.toml`, `pom.xml`, `*.csproj`, `package.json` at clone root. Confidence ceiling: 0.90 package-level facts. Do NOT use for: class-level or method-level claims.

### Step 4: Extract metadata and shortcode patterns (SP-3 + SP-4)

**Metadata patterns** (read 5+ nearest sibling or parent pages):
- Classify each frontmatter field as: Required (100% of pages), Common (>50%), Optional (<50% but observed)
- Do NOT classify `provenance:` or `evidence:` blocks as optional -- AGENTS.md section 5 mandates them on all non-structural content pages regardless of local pattern
- Record in `metadata_pattern.json` (internal reference for SP-9 proposals)

**Shortcode patterns** (grep target section and 2 parent levels for `{{<`):
- Classify: observed-mandatory (100% of index or leaf pages), observed-common (>50%), optional (<50%), forbidden-not-observed
- FAQ: if `## FAQ` heading in >50% of leaf pages, it is observed-common; propose for new leaf pages
- Conclusion: if `## Conclusion` in >50% of leaf pages, it is observed-common; propose for new leaf pages
- If pattern not observed, do NOT propose it
- Record in `shortcode_pattern.json` (internal reference for SP-9 proposals)

### Step 5: Build clone-cache mental model (SP-5)

1. Verify clone cache root does not contain `foss-launcher`:
   - Use `scripts/pipeline/core/clone_cache.py:cache_root()` to get resolved absolute path
   - If `foss-launcher` or `foss_launcher` appears anywhere in resolved absolute path string: set `STALE_CLONE_CACHE_PATH` in manifest; log error; continue in knowledge-only mode; confidence ceiling 0.70 <!-- PROHIBITION_OBSOLETE_FOSS_LAUNCHER_REFERENCE -->
   - Record `clone_cache_contains_foss_launcher: false` (or `true` if detected)

2. For each clone candidate:
   - Verify `runs/.clone_cache/aspose_{family}_{platform}/` exists (absolute path)
   - If missing: log `clone_missing: true`; continue with knowledge artifacts only; confidence ceiling 0.70

3. Scoped inspection only (do NOT scan entire clone):
   - Read `README.md` or `README.rst` at clone root
   - Read one package metadata file (Adapter H)
   - For each topic area in section inventory: grep `src/` or equivalent for class/method names from `api_surface.json` -- targeted grep only
   - List `samples/` or `examples/` or `tests/` directory (listing only)

4. Record clone SHA: conceptually equivalent to `git -C {clone_path} rev-parse HEAD`

5. Write `reports/section-enhance/{section-slug}/02-clone-cache-truth-map.md`.

### Step 6: Load knowledge artifacts (SP-6)

- Check `knowledge/{family}/{platform}/merged/model.yaml` for `stale_since`
  - If not null: add `knowledge_stale: true` to manifest; apply confidence ceiling 0.70 to all proposals; note in risk report; do NOT halt
- Read: `api_surface.json`, `claims.json` (filtered to section-relevant topics by keyword match), `formats.json`, `limitations.md`
- Read `snippets/` directory listing (and relevant snippet files for section topics)
- For multi-clone targets: load knowledge for each applicable family/platform

### Step 7: Detect gaps (SP-7)

Check all gap types. Each finding includes: `{gap_type, severity (high/medium/low), file_or_directory, evidence_basis, confidence, proposed_fix_type}`.

| Gap type | Detection method | Severity |
|---|---|---|
| Missing index page | `_index.md` absent from target directory | High |
| Missing child pages | Topics in api_surface.json claim categories with no matching page | Medium |
| Missing subsection | Section of claims.json categories with no coverage | Medium |
| Missing code examples | Pages with API references but zero code blocks | Medium |
| Missing FAQ section | FAQ pattern is observed-common (SP-4) but page lacks it | Low |
| Missing conclusion | Conclusion pattern is observed-common (SP-4) but page lacks it | Low |
| Missing child-listing shortcode | Index page with children but `{{< children >}}` is observed-mandatory and absent | High |
| Missing related links | Observed-common pattern but page has none | Low |
| Inconsistent metadata | Required-tier fields from SP-3 absent from a specific page | Medium |
| Invalid filename | Fails filename regex | High (blocks proposals adding more violations) |
| Duplicate/overlapping topics | Two pages share >70% keyword overlap from section headings | Low |
| Placeholder/shallow content | Page under 150 words with no code blocks | Medium |
| Outdated terminology | API name in page not matching api_surface.json (potential rename) | Medium |
| Unsupported API claims | Class/method name in page not found in api_surface.json | High |
| Orphan pages | Page not linked from parent index and not referenced elsewhere | Medium |
| Protected page gap | Gap in `auto_updatable: false` page | Flagged for human; no proposal generated |

Write `reports/section-enhance/{section-slug}/03-gap-report.md` and `03-gap-report.json`.

Zero gaps is a valid outcome. The gap report must explain the detection methodology regardless of count.

### Step 8: Rank candidates (SP-8)

- Score each gap: severity_weight x evidence_strength_weight x fix_type_weight
- Group by fix type: new-page, section-addition, metadata-fix, shortcode-fix, content-expansion
- Assign confidence per evidence tier:

| Tier | Sources | Confidence | Draft behavior |
|---|---|---|---|
| Strong | Clone-cache grep + api_surface.json + approved snippet | >= 0.85 | Full body draft (if --mode draft) |
| Medium-high | api_surface.json match + claims.json support + no limitations.md contradiction | 0.70-0.84 | Section outline only |
| Medium | claims.json supports topic + sibling-content pattern matches | 0.60-0.69 | Headings + brief descriptions |
| Weak | Topic in README or existing page titles but no API confirmation | 0.40-0.59 | Heading list only; human supplies prose and code |
| Insufficient | No evidence in any adapter | < 0.40 | Not proposed; logged as skip in gap report |

Mark as human-review-mandatory when:
- Target page has `auto_updatable: false`
- knowledge `stale_since` is not null AND clone is missing
- Clone mapping is ambiguous
- Confidence < 0.60
- `limitations.md` contradicts a feature claim
- Any subsection addition to an existing page (conservative in Phase 1)

Write `reports/section-enhance/{section-slug}/04-candidate-list.md`. Zero candidates is a valid success.

### Step 9: Generate proposals (SP-9)

For each candidate with confidence >= 0.40:

**New page proposals**:
- Derive slug: kebab-case from topic name; validate regex `^[a-z][a-z0-9-]*$`; must not start with hyphen
- Derive file path: `content/{subdomain}{en_segment}/{family}/{platform_segment}/{section}/{slug}.md`
  - `en_segment`: `/en` for docs/kb/products/reference; empty for blog
  - `platform_segment`: `/{platform}` for platform-level; empty for family-level
- Derive frontmatter from SP-3 Required + Common fields only
- Always include governance-mandatory blocks (AGENTS.md section 5):
  - `provenance:` block: `content_origin: skill-generated`, `last_mechanism: skill`, `auto_updatable: true`, `content_created_at: '{today}'`
  - `evidence:` block skeleton with matching claim IDs and API names
- Confidence >= 0.85 AND `--mode draft`: generate full content body (headings, prose, code from `snippets/` or clone examples)
- Confidence 0.60-0.84 OR `--mode audit`: section outline (headings + brief descriptions)
- Confidence 0.40-0.59: heading list only; note human must supply prose and code
- Shortcodes: copy exact syntax from SP-4 `shortcode_pattern.json`; never invent shortcode names

**Section addition proposals**:
- Specify: target file path, heading anchor, insertion position, heading level and text
- Include evidence reference; note confidence
- If `auto_updatable: false`: flag for human review only; do not propose body changes

**Metadata fix proposals**:
- Specify: target file path, field name, exact proposed value, derivation from SP-3 pattern
- Classify as: safe (adding missing optional field) or needs-review (modifying existing field)

Write one file per proposal under `reports/section-enhance/{section-slug}/05-proposals/{slug}-proposal.md`.

### Step 10: Run verification gates (SP-10)

Before finalizing any proposal, check all gates:

| Gate | Check |
|---|---|
| Stale-path | Resolved clone path does not contain `foss-launcher` |
| Filename | Proposed filename passes `^(_index|index(\.[a-z]{2,3})?|[a-z][a-z0-9-]*)\.md$` |
| Slug | Derived slug passes `^[a-z][a-z0-9-]*$`; no leading or trailing hyphen |
| Metadata field | Every proposed frontmatter key in SP-3 pattern OR governance-mandatory (provenance, evidence) |
| Shortcode | Every `{{< {name} >}}` in proposal exists in SP-4 pattern |
| Evidence | At least one claim_id or API name supports proposed topic; demote or remove if insufficient |
| API name | Every class/method token in proposed code blocks appears in `api_surface.json` |
| Link | Any cross-links point to existing content pages or other proposals in this pack |
| Conflict | Proposed file path does not already exist under `content/` |
| Auto-updatable | Target page has `auto_updatable: true` OR finding is flagged human-review-only |

Remove or demote any proposal that fails a gate. Write `reports/section-enhance/{section-slug}/08-verification-checklist.md`.

### Step 11: Write supporting artifacts

- `reports/section-enhance/{section-slug}/06-evidence-map.json` -- evidence citations per proposal
- `reports/section-enhance/{section-slug}/07-risk-report.md` -- risks per proposal; multi-clone ambiguity; stale knowledge; zero-clone mode
- `reports/section-enhance/{section-slug}/09-handoff-notes.md` -- downstream skill invocations (see below); survival warning

**Handoff downstream skills** (human approval mandatory before any write):
- docs new page: `/new-docs-page` (S-56)
- kb how-to: `/new-kb-howto` (S-58)
- kb faq: `/new-kb-faq` (S-59)
- reference: `/new-reference-page` (S-60)
- blog: `/new-blog-post` (S-57)
- products: `/new-products-page` (S-61)
- section addition: `/manual-edit` (S-73) with proposal as specification
- After all writes: `/content-check` (S-23) -> `/eval-page` (S-25) -> `/commit` (S-76)

**Survival warning**: `reports/section-enhance/` is gitignored. Human must externally preserve approved proposals before session ends or git operations discard them.

### Step 12: Report

```
SECTION ENHANCE -- {canonical_path}
Mode: {audit|draft}
Section type: {section_type}
Clone: {found|missing|ambiguous}
Knowledge: {current|stale since {date}|absent}

Section inventory: {N} pages ({index_count} index, {leaf_count} leaf, {flagged_count} flagged)

Gap detection: {N} gaps found ({high_count} high, {medium_count} medium, {low_count} low)

Proposals: {N} generated ({draft_count} full draft, {outline_count} outline, {heading_count} headings-only)
  Removed by verification gates: {N}
  Human-review-only: {N}

Output: reports/section-enhance/{section-slug}/
  00-run-manifest.json
  01-section-inventory.md
  02-clone-cache-truth-map.md
  03-gap-report.md + 03-gap-report.json
  04-candidate-list.md
  05-proposals/ ({N} files)
  06-evidence-map.json
  07-risk-report.md
  08-verification-checklist.md
  09-handoff-notes.md

Next step: human reviews and approves proposals; then invoke downstream creation skills per 09-handoff-notes.md
```

> **Skill context close** -- run after the last step:
> ```bash
> PYTHONPATH=scripts/pipeline .venv/Scripts/python scripts/pipeline/commands/governance/skill_context.py end --skill S-96 --status completed
> ```

## Post-conditions
- `reports/section-enhance/{section-slug}/` written with all 10 artifact files
- Zero files written under `content/`
- All proposals pass SP-10 verification gates
- Run manifest records all alias corrections, clone status, knowledge freshness, and timestamps
- Zero proposals is a valid complete success if gap report explains methodology

## Error handling

| Error | Cause | Fix |
|---|---|---|
| Path not found after alias resolution | Input target does not match any known content path | Check input; use known repo path pattern from CLAUDE.md |
| `STALE_CLONE_CACHE_PATH` | Clone cache absolute path contains `foss-launcher` | Check `ASPOSE_CLONE_CACHE` env var; use default cache at `runs/.clone_cache/` |
| Clone missing | `runs/.clone_cache/aspose_{family}_{platform}/` does not exist | Run `/knowledge-update {family} {platform}` to populate clone; skill continues in knowledge-only mode with confidence ceiling 0.70 |
| Knowledge absent | `knowledge/{family}/{platform}/merged/` missing | Run `/knowledge-update {family} {platform}`; without knowledge, only structural gaps can be detected |
| Knowledge stale | `stale_since` not null in model.yaml | Run `/knowledge-diff {family} {platform}` then `/knowledge-update {family} {platform}`; skill continues with stale knowledge at confidence ceiling 0.70 |
| Ambiguous clone mapping | Multiple families/platforms match target | Provide `--family` and `--platform` flags to disambiguate |
| Proposal fails verification gate | API name not in api_surface.json, invalid slug, invented shortcode | Proposal removed from pack; reason recorded in 08-verification-checklist.md; not a fatal error |
| `PRECONDITION FAILED: api_surface.json not found` | Knowledge not bootstrapped | Run `/knowledge-update {family} {platform}` |

## Related skills
- S-21 `/page-enhance` -- single-page enhancer; use when targeting one specific page instead of a section
- S-43 `/gap-eval` -- verifies existing content claims against clone cache; use before section-enhance to understand current claim accuracy
- S-44 `/gap-plan` -- generates fix specs from gap-eval NOT-PUBLISHABLE verdicts; complementary to section-enhance
- S-12 `/knowledge-diff` -- detects knowledge staleness; run first if `stale_since` is not null
- S-14 `/knowledge-update` -- refreshes knowledge artifacts from clone cache; run if knowledge is stale or absent

---

## LLM Metrics Obligation

If this skill invokes `llm.professionalize.com` directly or through `LLMRouter`,
the run carries a **metrics obligation** (METRICS-PLAN-001, `AGENTS.md §15`):

- All professionalize calls must use `ProfessionalizeClient`, `LLMRouter`, or a
  registered adapter entry in `metrics_callsite_registry.yaml`.
- Each run must capture per-call `MetricsEvent` records and aggregate them into a
  validated `MetricsRow` via `RunMetrics`.
- Default mode is **dry-run**. Live posting requires explicit owner approval and
  `AGENT_METRICS_ENDPOINT` / `AGENT_METRICS_TOKEN` set locally.
- Non-professionalize calls (Gemini, Ollama, M2M) are excluded from
  `token_usage` and `api_calls_count`.
- Metrics failures must not crash or block the parent pipeline job.
