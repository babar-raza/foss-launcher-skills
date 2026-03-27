Translate one page or a full family/platform batch to the specified locales.

**Arguments:** `$ARGUMENTS`

## Routing

Inspect `$ARGUMENTS` to determine which skill to invoke:

- If `$ARGUMENTS` begins with a file path (contains `.md` or starts with `content/`):
  → Invoke the **translate-page** skill:
  ```
  /translate-page {src_path} {locales}
  ```
  where `{locales}` is the second token in `$ARGUMENTS` (default: `all` if omitted).

- Otherwise, treat `$ARGUMENTS` as `{family} {platform} [{site}] [{locales}]`:
  → Invoke the **translate-batch** skill:
  ```
  /translate-batch {family} {platform} [{site}] [{locales}]
  ```

## Quick Reference

| Invocation | Effect |
|---|---|
| `/translate content/docs.aspose.org/en/slides/net/getting-started/_index.md fr,de` | Translate one page to French and German |
| `/translate content/docs.aspose.org/en/slides/net/getting-started/_index.md all` | Translate one page to all 36 locales |
| `/translate slides net` | Batch-translate all Slides .NET docs to all locales |
| `/translate slides net docs.aspose.org fr,de,ar` | Batch-translate Slides .NET docs site to three locales |
| `/translate 3d python all all` | Batch-translate all 3D Python content across all sites |

## Flags

The underlying CLI supports these flags — pass them after the arguments when needed:

- `--dry-run` — validate without writing output files
- `--force` — re-translate even if translated files are already newer than source (batch only)
- `--offline` — use M2M100 local backend instead of the LLM API
- `--model MODEL` — override the translation model (page only)

## Environment

Requires `LLM_API_KEY` to be set in the environment unless `--offline` is used.
The translation cache is stored at `data/translation_cache.db`.
Flush cache with: `python -m translator flush-cache [--lang LANG]`
View cache stats with: `python -m translator cache-stats`
