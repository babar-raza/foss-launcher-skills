# S-37: Corpus Scan — Build Golden Corpus Profile

**Arguments**: $ARGUMENTS
Expected format: `{family} {platform} {site-type}`
Valid site types: `docs` | `blog` | `kb` | `products` | `reference`

## Purpose
Scan existing content pages in the external content repo, extract structural and stylistic patterns, merge golden corpus data (structural contracts, style rubrics, variant selection), and produce an enriched corpus profile. Generation skills (new-docs-page, new-blog-post, etc.) reference this profile for structural consistency and style anchoring.

## Content Repo Resolution
The content repo root is determined by (in priority order):
1. `$CONTENT_REPO_PATH` environment variable
2. `content_repo` in `config.yaml`
3. Current working directory

## Pre-conditions
1. Content repo must be configured and accessible
2. The content directory for the given site type must exist and contain `.md` files
3. Golden index should exist at `golden/_index.json` (run `python scripts/golden_index.py` if missing — the scan will still work without it but produce a less useful profile)

## Automated Script

```
python scripts/corpus_scan.py {family} {platform} {site-type}
```

## Manual Steps (fallback)

1. **Resolve content path**: Using `config.yaml` site templates, build the full path:
   e.g. `{content_repo}/content/docs.aspose.org/en/{family}/{platform}/`

2. **Scan pages**: List all `.md` files recursively. For each file:
   - Parse frontmatter fields and values
   - Count H2 and H3 headings, record their text
   - Count code blocks and their language identifiers
   - Detect Hugo shortcode usage
   - Check for `---` section dividers
   - Compute word count

3. **Filter**: Exclude pages with fewer than `golden_corpus.min_words` words (default: 200)

4. **Aggregate profile**:
   - Frontmatter schema: which fields appear in >50% of pages (required) vs. fewer (optional)
   - Section patterns: typical H2/H3 count, common section names, divider usage
   - Code style: most common languages, average blocks per page, average block length
   - Shortcodes: most frequently used Hugo shortcodes

5. **Select golden examples**: Pick the top N pages by word count (N = `golden_corpus.sample_count`, default: 3)

6. **Merge golden corpus data**: Load `golden/_index.json` and extract:
   - `golden_anchors` — matching golden pages for this site type with roles, variants, grades, word counts
   - `golden_structural_contracts` — per-section structural requirements (block types, code counts, word targets)
   - `golden_style_rubric` — writing standards (prose-before-code, use-case-required, code-completeness)
   - `available_variants` — which depth variants exist (minimal, standard, steps)
   - `richness_tier` — A/B/C based on published page count and API surface size
   - `selected_variant` — which variant to use for generation based on richness tier

7. **Write profile** to `knowledge/{family}/{platform}/_corpus/{site-type}_profile.json`

## Output

```
CORPUS SCAN — {family}/{platform} [{site-type}]
Content dir: {resolved_path}
Pages found: {n}
Golden examples: [{paths}]
Golden anchors: {count}
Richness tier: {A|B|C} → variant: {selected_variant}
Common sections: [{section_names}]
Profile written: knowledge/{family}/{platform}/_corpus/{site-type}_profile.json
```

## Post-conditions
- Profile JSON exists at `knowledge/{family}/{platform}/_corpus/{site-type}_profile.json`
- Profile contains `golden_examples` list with paths to the best existing pages
- Profile contains `golden_anchors`, `golden_structural_contracts`, `golden_style_rubric` from golden corpus (if golden index available)
- Profile contains `richness_tier` and `selected_variant` for tier-aware generation
- Generation skills can load this profile for structural consistency and style anchoring
