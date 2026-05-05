# Translation Backends — Configuration Reference

## Primary Backend: llm.professionalize.com (`LLMBackend`)

The default backend. Uses the OpenAI-compatible `/v1/chat/completions` endpoint at llm.professionalize.com.

### Environment Variables

| Variable | Required | Default | Description |
|---|---|---|---|
| `LLM_API_KEY` | **Yes** | — | Bearer token for llm.professionalize.com |
| `LLM_API_BASE_URL` | No | `https://llm.professionalize.com/v1` | Override the base URL (useful for staging) |
| `TRANSLATE_PRIMARY_MODEL` | No | `professionalize_llm` | Model ID for single-segment translation |
| `TRANSLATE_BULK_MODEL` | No | Same as `TRANSLATE_PRIMARY_MODEL` | Model ID for batch translation; falls back to primary if unset |

### Behaviour

- **Temperature:** always `0.1` — deterministic output for idempotent cache keys
- **Availability check:** `GET /models` at startup; HTTP 200 or 401 both count as reachable (401 = bad key, but endpoint is up)
- **Batch packing:** `translate_batch()` packs up to 20 segments per LLM call using a numbered prompt format (`1. text`, `2. text`, …). If the response cannot be parsed back into the expected number of items, falls back to per-segment calls.
- **Retry policy:** 3 attempts with exponential backoff — 2 s, 4 s, 8 s (base delay × 2^attempt). Retried on HTTP 429, 500, 502, 503, 504, connection errors, and timeouts.
- **Timeout:** 30 s per HTTP request
- **Max tokens:** 4096 per response

### System Prompt (single segment)

```
You are a professional technical translator. Translate the following from {src_lang} to {tgt_lang}.
Rules:
- Output ONLY the translation. No explanations, notes, or commentary.
- Preserve all formatting: markdown syntax, HTML tags, code blocks, links.
- Preserve all Hugo shortcodes exactly: {{< ... >}} and {{% ... %}}
- Keep all technical terms, brand names (Aspose), and API identifiers unchanged.
- Keep all archive/format names unchanged: ZIP, PDF, DOCX, PPTX, FBX, OBJ, GLTF, etc.
- Maintain the same tone and register as the source.
- Do not add, remove, or reorder content.
```

The batch variant uses the same rules but adds: `Output ONLY the translations, keeping the same numbering format (1., 2., 3., etc.)`.

---

## Fallback Backend: Ollama Local (`OllamaBackend`)

Used when the primary LLM backend fails after all retries.

### Environment Variables

| Variable | Required | Default | Description |
|---|---|---|---|
| `TRANSLATE_OLLAMA_BASE_URL` | No | `http://localhost:11434` | Ollama server URL |
| `TRANSLATE_OLLAMA_MODEL` | No | `llama3.2` | Ollama model to use |

### Behaviour

- **Auto-detection:** `is_available()` sends `GET /api/tags` with a 3 s timeout at first use. Result is cached for the lifetime of the process. If Ollama is not running, `BackendRouter` silently skips this backend.
- **Activation:** `BackendRouter` reaches `OllamaBackend` after `LLMBackend` raises `BackendUnavailableError` on all 3 retries.
- **API:** Uses Ollama's `/api/chat` endpoint with `"stream": false`.
- **Temperature:** `0.1` (same as primary, for consistency)
- **Retry:** 3 attempts with same exponential backoff as primary
- **Batch:** No native batch packing; falls back to sequential `translate()` calls via the `TranslationBackend` base class default

### Requirements

Ollama must be installed and running locally with a model pulled:

```bash
ollama pull llama3.2
ollama serve
```

---

## Offline Backend: M2M100 (`M2MBackend`)

Facebook's M2M100 multilingual translation model. Runs entirely locally with no API calls.

### Activation

```bash
# Via CLI flag:
python -m translator batch --family slides --platform net --site docs.aspose.org --locales all --offline

# Via environment variable:
TRANSLATE_OFFLINE=1 python -m translator batch ...
```

### Installation

NOT included in `requirements.txt`. Must be installed separately:

```bash
pip install transformers torch
```

### Configuration

No environment variables. Model name is hard-coded to `facebook/m2m100_418m`. On first use the model is downloaded by `transformers` (auto-cached in `~/.cache/huggingface/`).

### Behaviour

- **Lazy loading:** Model and tokenizer are loaded on the first `translate()` call, not at import time. This allows `M2MBackend` to be imported even when `transformers` is not installed — `ImportError` is raised only when translation is actually attempted.
- **If transformers missing:** Raises `ImportError` with a helpful message pointing to `pip install transformers torch`.
- **Batch efficiency:** `translate_batch()` encodes all segments together and calls `model.generate()` once with padding, taking advantage of GPU/CPU parallelism.
- **Language coverage:** Supports all 36 aspose.org locales via M2M100's built-in language codes (ISO 639-1 passthrough for most codes).
- **Max segment length:** 512 tokens (tokeniser truncation). Very long body segments may be silently truncated — prefer LLM backend for content pages, M2M100 for initial locale directory seeding.

### Best Use Case

Seeding a new locale directory where high volume is more important than LLM-quality output. A follow-up pass with `translate-batch` using the LLM backend will overwrite poor M2M100 output for any segment that has changed or has a quality issue.

---

## Backend Routing Decision Logic

```python
# Pseudocode — actual implementation in backends/base.py BackendRouter

def build_backend_chain(offline: bool) -> BackendRouter:
    if offline or os.environ.get("TRANSLATE_OFFLINE") == "1":
        return BackendRouter([M2MBackend()])

    backends = []

    # Primary: always attempted first if LLM_API_KEY is set
    if os.environ.get("LLM_API_KEY"):
        backends.append(LLMBackend())

    # Fallback: added if Ollama appears to be running
    ollama = OllamaBackend()
    if ollama.is_available():
        backends.append(ollama)

    if not backends:
        raise ConfigurationError("No backend available: set LLM_API_KEY or start Ollama")

    return BackendRouter(backends)

# At translation time:
def translate(text, src_lang, tgt_lang):
    for backend in self.backends:
        try:
            return backend.translate(text, src_lang, tgt_lang)
        except BackendUnavailableError:
            log.warning(f"{backend} unavailable, trying next")
    raise BackendUnavailableError("All backends failed")
```

---

## Cache Interaction

All three backends interact with the same `TranslationCache` instance. The cache layer sits above the backend router:

```
request(site_id, src_lang, tgt_lang, text)
  │
  ▼
cache.lookup()  ──► HIT → return cached value immediately (no backend call)
  │ MISS
  ▼
BackendRouter.translate() / translate_batch()
  │
  ▼
cache.store(result)
  │
  ▼
return result
```

Cache key: `SHA-256(site_id + ":" + src_lang + ":" + tgt_lang + ":" + normalised_text)`. Text is normalised by collapsing internal whitespace before hashing — minor reformatting of source content does not invalidate entries.

Running the same translation command twice is safe: the second run hits the cache for every segment and writes no new content (the file diff will be empty because `reconstruct_and_write` produces identical YAML and body). This is the idempotence guarantee.
