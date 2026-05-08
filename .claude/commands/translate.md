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

> **Parallelism note:** If this skill is invoked for multiple batches concurrently,
> each batch agent MUST NOT commit or push independently. See "Push Coordination"
> section in translate-batch SKILL.md. A single coordinator or the human operator
> must perform the final commit+push after all batches complete.

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
