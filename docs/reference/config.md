# Configuration Reference

Status: Current
Audience: Operator, Contributor, Agent
Canonical reference: this page
Last code-backed audit: 2026-05-30

This page owns configuration facts. Guides must link here instead of repeating config tables.

## Environment Loading

| Key/file | Default/source | Loaded by | Notes |
|---|---|---|---|
| `.env` | Repo root `.env` | `scripts/pipeline/core/env_loader.py` | Loaded with shell environment taking precedence. |
| Python dotenv dependency | Optional | `load_env()` | Missing `python-dotenv` is a no-op; shell vars still work. |

## Clone Cache

| Key | Default | Loaded by | Contract |
|---|---|---|---|
| `ASPOSE_CLONE_CACHE` | `<repo>/runs/.clone_cache` | `scripts/pipeline/core/clone_cache.py` | Optional override for FOSS clone cache. Must not point at retired cache locations. |
| `data/products.json` | Committed registry | `clone_cache._get_clone_url()` and discovery/update scripts | Provides `family`, `platform`, `repo_url`, `clone_url`, `active`. |

## LLM Routing

Canonical config: `scripts/pipeline/config/llm_registry.yaml`.

| Provider | Priority | Base URL | Env keys | Defaults |
|---|---:|---|---|---|
| `professionalize` | 1 | `https://llm.professionalize.com/v1` | endpoint override key and API key keys defined in registry | chat model `gpt-oss`; embedding model `qwen3-embedding-8b` |
| `ollama` | 2 | `http://localhost:11434/v1` | no API key | chat model `llama3.2`; embeddings `nomic-embed-text` |

`scripts/pipeline/commands/ops/llm_router.py` loads the registry and sorts providers by priority. It returns structured `CallResult` objects for call outcomes.

## Metrics Config

| File | Purpose |
|---|---|
| `scripts/pipeline/config/metrics_taxonomy.yaml` | Taxonomy for metrics rows. |
| `scripts/pipeline/config/metrics_callsite_registry.yaml` | Registered professionalize call sites. |
| `reports/metrics/events/` | Local JSONL event ledger output. |

Metrics events and rows are defined in [metrics reference](metrics.md).

## Test Config

`pytest.ini` defines:

| Setting | Value |
|---|---|
| `testpaths` | `tests`, `scripts/pipeline/tests`, `scripts/translator/tests` |
| `pythonpath` | `scripts/pipeline`, `scripts/translator` |

See [Testing and CI](../development/testing.md).

## Hugo Configs

| Site | Config |
|---|---|
| `www.aspose.org` | `configs/www.aspose.org.toml` |
| `products.aspose.org` | `configs/products.aspose.org.toml` |
| `docs.aspose.org` | `configs/docs.aspose.org.toml` |
| `kb.aspose.org` | `configs/kb.aspose.org.toml` |
| `reference.aspose.org` | `configs/reference.aspose.org.toml` |
| `blog.aspose.org` | `configs/blog.aspose.org.yml` |
| `websites.aspose.org` | `configs/websites.aspose.org.toml` |
