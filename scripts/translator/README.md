# translator — Hugo Multi-Site Translation Subsystem

This package translates Aspose documentation pages from English into 36 supported locales. It is field-selective (only translates the fields declared in `policy/fields.yaml`), evidence-safe (the `evidence` block is always preserved verbatim), and idempotent (a second run over already-translated content produces no diff). It drives translation through an LLM backend with Ollama local fallback and an optional offline M2M100 path, writing output atomically to Hugo content directories.

## Requirements

The core translator requires only `pyyaml` and `requests` (for LLM/Ollama backends).
Use the repo's `.venv` (set up via `/getting-started`):

```bash
# Install translator dependencies into the repo venv
.venv/Scripts/pip install -r scripts/translator/requirements.txt
```

For the optional offline M2M100 backend only:

```bash
.venv/Scripts/pip install transformers torch
```

## Environment Variables

| Variable | Required | Default | Description |
|---|---|---|---|
| `LLM_API_KEY` | Yes (primary) | — | API key for llm.professionalize.com |
| `LLM_API_BASE_URL` | No | `https://llm.professionalize.com/v1` | Override primary LLM endpoint |
| `TRANSLATE_PRIMARY_MODEL` | No | `professionalize_llm` | Model for single-segment translation |
| `TRANSLATE_BULK_MODEL` | No | Falls back to `TRANSLATE_PRIMARY_MODEL` | Model for batch translation |
| `TRANSLATE_OLLAMA_BASE_URL` | No | `http://localhost:11434` | Ollama server URL |
| `TRANSLATE_OLLAMA_MODEL` | No | `llama3.2` | Ollama model to use |
| `TRANSLATE_OFFLINE` | No | `0` | Set to `1` to force the M2M100 offline backend |
| `TRANSLATE_CACHE_DB` | No | `cache/translation_cache.db` | Path to the SQLite cache file (gitignored) |

## CLI Usage

All commands are run from the repo root as a Python module.

### Translate a single page

```bash
python -m translator page content/docs.aspose.org/en/slides/net/_index.md \
  --locales fr,de,ar \
  [--model professionalize_llm] \
  [--dry-run]
```

`--dry-run` prints what would be written without touching the filesystem.

### Translate a batch (family/platform/site)

```bash
python -m translator batch \
  --family slides \
  --platform net \
  --site docs.aspose.org \
  --locales all
```

`--locales all` expands to all 36 supported locale codes. Accepts a comma-separated subset (e.g. `--locales fr,de,ja`).

### Sync untranslated pages

Walks English source pages and translates any locale copy that is missing or out of date:

```bash
python -m translator sync [--family FAMILY] [--platform PLATFORM]
```

Without filters, sync covers all families and platforms.

### Flush the translation cache

```bash
python -m translator flush-cache [--lang LANG]
```

Without `--lang`, flushes all entries. With `--lang fr`, flushes only French entries.

### Show cache statistics

```bash
python -m translator cache-stats
```

Prints total entries, total cache hits, and a breakdown by target language.

## Package Structure

```
scripts/translator/
├── __init__.py              # Version, locale list, base exceptions
├── requirements.txt         # Base runtime dependencies
│
├── policy/
│   ├── fields.yaml          # Per-content-type field translation rules
│   ├── patterns.yaml        # Body protection regex patterns + placeholder format
│   └── loader.py            # ContentTypePolicy.for_path() — detects content type
│
├── parser/
│   ├── document.py          # HugoDocument dataclass + parse_file / parse_string
│   ├── frontmatter.py       # iter_translatable_fields / set_field (nested path walker)
│   └── protector.py         # protect() / restore() placeholder system
│
├── backends/
│   ├── base.py              # TranslationBackend ABC + BackendRouter + retry helper
│   ├── llm.py               # LLMBackend (llm.professionalize.com, batch packing)
│   ├── ollama.py            # OllamaBackend (local Ollama, auto-detected)
│   └── m2m.py               # M2MBackend (offline facebook/m2m100_418m, lazy-load)
│
├── cache/
│   └── sqlite_cache.py      # TranslationCache — SHA-256 keyed SQLite store
│
├── engine/
│   └── __init__.py          # (translation orchestration — populated by Agent D CLI)
│
├── validation/
│   └── __init__.py          # (evidence and placeholder validation hooks)
│
└── writer/
    └── reconstructor.py     # reconstruct_document / reconstruct_and_write (atomic)
```

## What Gets Translated vs Preserved

**Translated** (per content type — see `translation-policy.md` for full tables):
- `docs` / `kb` / `reference`: `title`, `description` (and `keywords` / `linkTitle` where applicable)
- `products`: `family_name`, `plugin_description`, `head_title`, `head_description`, `title`, `description`, and a set of nested fields under `overview`, `content`, `single`, `faq`, `testimonialswrapper`
- Body prose in all translatable content types

**Always preserved** (never translated):
- The entire `evidence` block (audit metadata)
- All structural frontmatter keys: `type`, `layout`, `weight`, `date`, `lastmod`, `draft`, `slug`, `url`, `aliases`, `github_url`, `enable`, `submenu`, `more_formats`, `back_to_top`, `supportandlearning`, `plugin_platform`, `platformkey`, `productkey`, `productplatform`, `categories`
- In the body: Hugo shortcodes, fenced code blocks, inline code, link URLs, block HTML

**Skipped entirely:**
- `blog.aspose.org` — English only, no locale directories exist

## Integration with Skills

Two Claude skills drive the translator in the agent workflow:

- **`translate-page`** — invokes `python -m translator page` for a single source file with specified locales
- **`translate-batch`** — invokes `python -m translator batch` for a full family/platform/site sweep

Both skills read the `evidence` block of the source file before calling the translator and verify it is intact in the output.
