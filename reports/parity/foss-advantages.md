# foss-launcher Advantages Over aspose.org

**Generated**: 2026-05-15  **Agent**: A (Discovery)  **Plan**: PAR-011

## 10 Unique Skills Not in aspose.org

| Slug | Foss ID | Description |
|------|---------|-------------|
| corpus-scan | S-37 | skills/corpus-scan.md |
| discover-products | S-39 | skills/discover-products.md |
| evidence-decide | S-43 | skills/evidence-decide.md |
| evidence-materialize | S-44 | skills/evidence-materialize.md |
| evidence-verify | S-46 | skills/evidence-verify.md |
| ground-check | S-23 | skills/ground-check.md |
| mental-model | S-45 | skills/mental-model.md |
| seo-review | S-109 | skills/seo-review.md |
| translate | S-107 | skills/translate.md |
| truth-sync | S-30 | skills/truth-sync.md |

## Infrastructure Advantages

| Advantage | aspose.org | foss-launcher |
|-----------|-----------|---------------|
| Standalone operation | No (Hugo dependency) | Yes |
| pyproject.toml entry points | 0 | 6 console_scripts |
| Registry format | JSON (verbose) | YAML (readable) |
| Test suite location | scripts/pipeline/tests/ (mixed) | tests/ (dedicated) |
| Skill ID range | S-01–S-97 | S-01–S-109 |
| Total skill count | 84 | 92 |

## Clean-Room Design Benefits

foss-launcher was designed as a standalone implementation, free from Hugo CMS coupling.
This enables deployment in any content pipeline without a full website infrastructure.
The simplified registry schema and consolidated test directory make it easier to
onboard contributors and maintain consistent quality.