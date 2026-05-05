# Translator Subsystem — Architecture

## Design Goals

| Goal | How it is achieved |
|---|---|
| **Self-contained** | Single Python package under `scripts/translator/`; no dependency on the broader pipeline. Base requirements are four pure-Python/HTTP libraries. |
| **Evidence-safe** | The `evidence` key is listed in `universal_preserve` in `fields.yaml` and explicitly guarded in every content-type policy. The reconstructor copies it verbatim; no translation path touches it. |
| **Field-selective** | `policy/fields.yaml` declares exactly which fields are translatable per content type. Everything not in the `translate` or `translate_nested` list is passed through unchanged. |
| **Skills-integrated** | The CLI surface (`python -m translator page / batch / sync`) is the exact interface called by the `translate-page` and `translate-batch` skills. No wrapper scripts required. |

## Module Diagram

```
ContentTypePolicy.for_path()
        │
        ▼
   [policy/]
   fields.yaml ──► loader.py ──► FieldPolicy, ContentTypePolicy
   patterns.yaml ──────────────► protected_patterns, placeholder_format

HugoDocument
        │
        ▼
   [parser/]
   document.py   ── parse_file() / parse_string()  ──► HugoDocument
   frontmatter.py ─ iter_translatable_fields()       ──► (path, value) pairs
                    set_field()                       ◄── translated values
   protector.py  ── protect()   ──► (masked_text, placeholder_map)
                    restore()   ◄── translated_text

Translation
        │
        ▼
   [cache/]
   sqlite_cache.py ── lookup() ──► cached hit (skip backend)
                      store()  ◄── new translation (persist)

   [backends/]
   base.py      ── BackendRouter.translate() / translate_batch()
   llm.py       ── LLMBackend      (primary)
   ollama.py    ── OllamaBackend   (fallback)
   m2m.py       ── M2MBackend      (offline)

Output
        │
        ▼
   [writer/]
   reconstructor.py ── reconstruct_document()     ──► string
                        reconstruct_and_write()    ──► atomic file write
```

## Data Flow

```
English .md file
       │
       ▼  parse_file()
  HugoDocument { frontmatter: dict, body: str }
       │
       ▼  ContentTypePolicy.for_path()
  Detect content type  ──►  skip if blog.aspose.org
       │
       ├──► iter_translatable_fields()  (frontmatter)
       │         │
       │         ▼  for each (path, value):
       │       cache.lookup() ──► hit → use cached value
       │             │ miss
       │             ▼
       │       backend.translate(value, "en", tgt_lang)
       │             │
       │             ▼
       │       cache.store()
       │             │
       │             ▼
       │       set_field(frontmatter, path, translated_value)
       │
       └──► body (if translate_body=true):
                 │
                 ▼  protect(body, patterns, placeholder_format)
           (masked_body, placeholder_map)
                 │
                 ▼  cache.lookup() / backend.translate()
           translated_masked_body
                 │
                 ▼  restore(translated_masked_body, placeholder_map)
           translated_body  ──► PlaceholderLeakError if any token missing
                 │
                 ▼
  HugoDocument { frontmatter: translated, body: translated_body }
       │
       ▼  validate: evidence block present and unchanged
       │
       ▼  reconstruct_and_write(doc, output_path)  ── atomic
  locale .md file written
```

## Why Placeholder Instead of AST

A proper AST parser (e.g. mistletoe, markdown-it-py) would require tracking node ranges through a full parse→transform→render cycle. Hugo markdown is not standard CommonMark — it embeds shortcodes (`{{< >}}`, `{{% %}}`), custom front-matter fields, and mixed HTML/markdown that renders differently depending on the Hugo theme. An AST approach risks misidentifying shortcode boundaries or corrupting list/table structure during re-serialisation.

The placeholder approach is simpler and sufficient: regex patterns cover the actually-problematic regions (shortcodes, code fences, inline code, URLs), replace them with opaque tokens before the LLM sees the text, and restore them after. The `PlaceholderLeakError` guard makes any token loss an immediate hard failure rather than silent corruption.

## Why SQLite Instead of LMDB+faiss

Translation caching requires only exact-match lookup (same site, same language pair, same normalised text). A vector index (faiss) is needed for approximate nearest-neighbour retrieval — unnecessary here. LMDB adds a C extension dependency and per-process read/write locking that complicates parallel runs.

SQLite with WAL journal mode provides:
- Exact SHA-256 keyed lookup in O(log n) via B-tree index
- Concurrent readers, serialised writers (sufficient for a CLI tool)
- `hit_count` tracking for cache analytics
- Zero installation overhead (stdlib `sqlite3`)
- `:memory:` mode for in-process tests

## Why Env-Var Config Instead of a Model Registry YAML

The repo already uses environment variables for all sensitive credentials (see `memory/reference_llm_infrastructure.md`). Adding a YAML model registry would require another loader, another schema, and another place to keep in sync. The four env vars that control backend selection (`LLM_API_KEY`, `TRANSLATE_PRIMARY_MODEL`, `TRANSLATE_BULK_MODEL`, `TRANSLATE_OFFLINE`) are sufficient to cover all production and CI scenarios and map directly onto the existing infrastructure documentation.

## Evidence Block Design

The `evidence` frontmatter key holds internal audit metadata (source URL, model, verification timestamp, etc.). It is defined in `AGENTS.md` as internal-only — never rendered to the public site. The translator treats it as:

1. Listed in `universal_preserve` in `fields.yaml` — excluded from every `translate` list
2. Explicitly called out with `# CRITICAL: never translate` comment in each content-type `preserve` list
3. `HugoDocument.has_evidence()` / `get_evidence()` allow validation code to confirm the block survived the round-trip unchanged
4. If evidence is present in the source but absent in the output, the validation step must reject the document

## Backend Router Design

`BackendRouter` holds an ordered list of `TranslationBackend` instances and tries them in sequence:

```
request
  │
  ├──► LLMBackend.translate()   ──► success → return result
  │         │ BackendUnavailableError (after 3 retries)
  │         ▼
  ├──► OllamaBackend.translate() ──► success → return result
  │         │ BackendUnavailableError
  │         ▼
  └──► BackendUnavailableError("All backends failed")
```

When `TRANSLATE_OFFLINE=1` or `--offline` is passed, `M2MBackend` is placed at position 0 and the LLM/Ollama backends are not instantiated.

`OllamaBackend.is_available()` checks `GET /api/tags` at startup (cached thereafter) so Ollama is silently skipped if not running — no error unless it is the last backend.

## Provenance Tracking

Every successful translation writes a `provenance:` YAML block to the output file's frontmatter via `scripts/pipeline/provenance.py`. This replaces the removed `_is_bot_authored()` git-history heuristic.

### Fields written on each translation

```yaml
provenance:
  translation_origin: translator-sync   # or translator-page / translator-batch / translator-retranslate
  source_file: docs.aspose.org/en/3d/python/_index.md
  source_sha: f83863516342              # SHA-256[:12] of English source content
  last_mechanism: translator
  auto_updatable: true
  reviewed: false
```

### Overwrite decision in `_cmd_sync`

```python
if tgt_path.exists() and not _prov.is_auto_updatable(tgt_path):
    print(f"[SKIP] {tgt_path} -- auto_updatable=false, requires review")
    continue
```

`is_auto_updatable()` reads the `auto_updatable` field from the provenance block. It defaults to `True` when no provenance block exists (migration default). This allows previously-blocked files to be processed after backfill.

**Never use git commit author email as a proxy for overwrite eligibility.** The `_is_bot_authored()` function was removed in commit `cdaa1daac`. It checked `git log --format=%ae -1 <file>` against `hugo-translator@aspose.net`, which is unreliable because any maintenance commit (evidence attach, grade write, frontmatter fix) changes the last commit author.

### Staleness detection

`source_sha` enables content-hash staleness detection. Compare it to `sha256(english_source)[:12]` to determine whether a locale file is out of date without relying on file modification times.

### Validation checker

`provenance` is added to `_NON_TRANSLATABLE_METADATA_KEYS` in `validation/checker.py` so the post-translation validator does not flag provenance block differences between source and target files as errors.

## Atomic Write Guarantee

`reconstructor._atomic_write()` uses Python's `tempfile.mkstemp()` in the same directory as the target file (same filesystem), writes the full content to the temp file, then calls `os.replace()`. On POSIX this is a kernel-level atomic rename. On Windows, Python 3.3+ maps `os.replace()` to `MoveFileExW` with `MOVEFILE_REPLACE_EXISTING`, which is atomic at the filesystem level. If the write fails at any point, the original file is untouched and the temp file is deleted in the `except` clause.
