# S-107: Translate — Translation Dispatcher

Translate one page or a full family/platform batch to the specified locales by routing to the existing translation skills.

**Arguments:** `$ARGUMENTS`

## Routing

Inspect `$ARGUMENTS` to determine which skill to invoke:

- If `$ARGUMENTS` begins with a file path, contains `.md`, or starts with `content/`, invoke:

  ```text
  /translate-page {src_path} {locales}
  ```

  `{locales}` is the second token in `$ARGUMENTS`. Default to `all` if omitted.

- Otherwise, treat `$ARGUMENTS` as `{family} {platform} [{site}] [{locales}]` and invoke:

  ```text
  /translate-batch {family} {platform} [{site}] [{locales}]
  ```

## Quick Reference

| Invocation | Effect |
|---|---|
| `/translate content/docs.aspose.org/en/slides/net/getting-started/_index.md fr,de` | Translate one page to French and German |
| `/translate content/docs.aspose.org/en/slides/net/getting-started/_index.md all` | Translate one page to all configured locales |
| `/translate slides net` | Batch-translate Slides .NET content to all configured locales |
| `/translate slides net docs.aspose.org fr,de,ar` | Batch-translate Slides .NET docs to three locales |
| `/translate 3d python all all` | Batch-translate all 3D Python content across all sites |

## Flags

Pass supported flags through to the underlying skill:

- `--dry-run` validates without writing output files.
- `--force` re-translates even if translated files already exist where supported.
- `--offline` or provider flags select an offline/local backend where supported.
- `--model MODEL` overrides the translation model where supported.

## Safety

- This dispatcher does not translate content directly.
- It must not write content itself.
- It inherits all dry-run, content-root, backend, evidence-preservation, and no-blog-translation rules from `translate-page` and `translate-batch`.
- Concurrent batch agents must not commit or push independently; final commit coordination belongs to the operator or a single coordinator.

## Environment

Translation backends may require `LLM_API_KEY` unless an offline provider is used. Missing production metrics credentials (`AGENT_METRICS_ENDPOINT`, `AGENT_METRICS_TOKEN`) must not block dry-run verification.

## Post-conditions

- Page-path invocations are delegated to `translate-page`.
- Family/platform invocations are delegated to `translate-batch`.
- Dispatcher behavior is covered by registry and provider mirror validation.
