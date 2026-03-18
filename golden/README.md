# Golden Corpus

Curated exemplar content files used as structural and stylistic reference for content generation skills. Every generation skill reads these files to anchor output consistency.

## Origin

Imported from the [foss-launcher](../README.md) orchestrator project. Use `scripts/refresh_golden.py` to pull updates.

## Directory Structure

```
golden/
├── blog.aspose.org/__FAMILY__/__PLATFORM__/       # Blog posts
├── docs.aspose.org/__FAMILY__/__PLATFORM__/        # Documentation
│   ├── developer-guide/                            # Feature docs (3 variants)
│   └── getting-started/                            # Installation, licensing
├── kb.aspose.org/__FAMILY__/__PLATFORM__/          # Knowledge base
│   └── howto (3 variants), faq, troubleshooting, feature-showcase
├── products.aspose.org/__FAMILY__/                 # Product landing pages
└── reference.aspose.org/__FAMILY__/__PLATFORM__/   # API reference (2 variants)
```

## Grade System

Each file carries a quality grade in its HTML comment header:

```html
<!-- GOLDEN REFERENCE | Structural Exemplar | Language: Python (structural only) | Original-Grade: A -->
```

| Grade | Meaning |
|-------|---------|
| A     | Comprehensive, expert-level with multiple examples and best practices |
| A-    | Excellent, complete with examples and deep coverage |
| B+    | Good, well-organized with helpful examples |
| B     | Solid, good structure with useful content |
| B-    | Acceptable, minor gaps or simplified structure |
| C     | Basic, minimal examples |

## Variant System

Files with `.variant-{type}` in their name provide different depth treatments of the same content type:

| Variant | When to use | Characteristics |
|---------|-------------|-----------------|
| `minimal` | Richness tier C (thin API, few classes) | Bare-bones, 1-2 KB, quick example only |
| `standard` | Richness tier A/B (default) | Full coverage, 15-25 KB, multiple examples, best practices |
| `steps` | KB how-to articles needing tutorial format | Numbered steps, progressive complexity |

Selection: `golden/_index.json` maps richness tiers to variants via `tier_selection`.

## Template Variables

Golden files use placeholder variables for platform-agnostic templating. These must NOT be resolved in the golden files themselves — they are structural placeholders:

| Variable | Purpose |
|----------|---------|
| `{{PRODUCT_NAME}}` | Full product name (e.g., "Aspose.Cells for Python") |
| `{{PRODUCT_FAMILY}}` | Family name (e.g., "Cells") |
| `{{PLATFORM}}` | Target platform (e.g., "Python") |
| `{{PACKAGE_NAME}}` | Package manager name (e.g., "aspose-cells-python") |
| `{{PACKAGE_MANAGER}}` | Install tool (e.g., "pip") |
| `{{REPO_URL}}` | Repository URL |
| `{{FAMILY}}` | Short family identifier |

## Page Roles

Each golden file maps to a page_role used by generation skills:

| Subdomain | Path pattern | page_role |
|-----------|-------------|-----------|
| docs | getting-started/installation | `installation` |
| docs | getting-started/license | `license` |
| docs | developer-guide/* | `workflow_page` |
| kb | howto* | `howto_article` |
| kb | faq | `faq` |
| kb | troubleshooting | `troubleshooting` |
| kb | feature-showcase | `feature_showcase` |
| blog | introducing-PRODUCT | `feature_blog` |
| reference | reference* | `api_reference` |
| products | * | `landing` |
| any | _index.md | `section_index` |

## Golden Index

Run `python scripts/golden_index.py` to regenerate `golden/_index.json`. This index contains:
- Parsed section structure with structural contracts (block types, word counts, code density)
- Style rubrics per page (prose-before-code, use-case requirements, code completeness)
- Role-to-variant mapping and tier selection rules

The index is committed to the repo so skills can read it without running Python.

## How Skills Use This Corpus

1. **Generation skills** load the golden index and read the matching golden file for the target page_role + variant
2. **Structural contracts** from the index specify minimum block types, code block counts, and word targets per section
3. **Anchor excerpts** (first 600 chars of matching sections) set voice and style
4. **Style rubrics** enforce patterns like prose-before-code and use-case bullets
5. **Evaluation** (eval-page S-25) scores golden conformance across 5 dimensions
6. **Healing** (heal-page S-26) uses golden references to fix structural divergence
