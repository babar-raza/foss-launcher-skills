#!/usr/bin/env python3
# Adapted from aspose.org
"""Shared LLM router for all pipeline modules.

Replaces the four independent ``_llm_call()`` implementations scattered across
enrich.py, run.py, fix_spec.py, and synthesize.py with a single routing layer
backed by ``llm_registry.yaml``.

Usage (library):
    from llm_router import LLMRouter, EndpointStatus
    router = LLMRouter()
    result = router.call_chat("You are helpful.", "Summarize this.")
    if result.status == EndpointStatus.OK:
        print(result.data)

Usage (CLI probe):
    python scripts/pipeline/lib/llm_router.py --probe
    python scripts/pipeline/lib/llm_router.py --probe --provider professionalize
"""

import argparse
import enum
import json
import logging
import os
import re
import sys
import time
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

try:
    import yaml  # type: ignore
except ImportError:
    yaml = None  # type: ignore[assignment]

try:
    import requests  # type: ignore
except ImportError:
    requests = None  # type: ignore[assignment]

try:
    from commands.ops.professionalize_client import ProfessionalizeClient  # type: ignore
    _PROF_CLIENT_AVAILABLE = True
except ImportError:
    _PROF_CLIENT_AVAILABLE = False

logging.basicConfig(level=logging.INFO, format="%(levelname)s: %(message)s")
log = logging.getLogger(__name__)

_REGISTRY_PATH = Path(__file__).resolve().parents[2] / "config" / "llm_registry.yaml"


# ---------------------------------------------------------------------------
# EndpointStatus enum
# ---------------------------------------------------------------------------

class EndpointStatus(str, enum.Enum):
    """Classification of an endpoint probe or call outcome."""
    OK = "ok"
    UNREACHABLE = "unreachable"
    AUTH_FAILED = "auth_failed"
    MODEL_MISSING = "model_missing"
    NOT_CONFIGURED = "not_configured"
    DISABLED_POLICY = "disabled_policy"
    INTENTIONAL_SKIP = "intentional_skip"
    PARSE_FAILED = "parse_failed"
    UNKNOWN = "unknown"


# ---------------------------------------------------------------------------
# CallResult dataclass
# ---------------------------------------------------------------------------

@dataclass
class CallResult:
    """Outcome of an LLM call (chat or embeddings).

    Never raises — every path returns a CallResult.
    """
    provider: str = ""
    endpoint: str = ""
    model: str = ""
    status: EndpointStatus = EndpointStatus.UNKNOWN
    data: Any = None
    latency_ms: float = 0.0
    http_status: int = 0
    error: str = ""
    fallback_artifact: str = ""
    token_usage: int = 0
    api_calls_count: int = 0
    metrics_events: list = field(default_factory=list)


# ---------------------------------------------------------------------------
# Registry loader
# ---------------------------------------------------------------------------

def _load_registry(path: Path | None = None) -> dict:
    """Load llm_registry.yaml. Raises RuntimeError on failure."""
    p = path or _REGISTRY_PATH
    if yaml is None:
        # Fallback: parse simple YAML with json-compatible loader
        # We need PyYAML — if missing, try a minimal parse
        raise RuntimeError(
            f"PyYAML required to load {p}. Install with: pip install pyyaml"
        )
    if not p.exists():
        raise RuntimeError(f"LLM registry not found: {p}")
    with open(p, encoding="utf-8") as fh:
        data = yaml.safe_load(fh)
    if not data or "providers" not in data:
        raise RuntimeError(f"Invalid LLM registry (missing 'providers'): {p}")
    return data


def _sorted_providers(registry: dict) -> list[tuple[str, dict]]:
    """Return providers sorted by priority (lowest number = first)."""
    providers = registry["providers"]
    return sorted(providers.items(), key=lambda kv: kv[1].get("priority", 99))


# ---------------------------------------------------------------------------
# Status mapper for ProfessionalizeClient results
# ---------------------------------------------------------------------------

def _map_prof_status(prof_result: Any) -> tuple:
    """Map ProfessionalizeCallResult fields to (EndpointStatus, error_str)."""
    if prof_result.ok:
        return EndpointStatus.OK, ""
    event_status = prof_result.event.status if prof_result.event else "failure"
    http = prof_result.http_status or 0
    if event_status == "timeout":
        return EndpointStatus.UNREACHABLE, prof_result.error_summary or "timeout"
    if http in (401, 403):
        return EndpointStatus.AUTH_FAILED, f"HTTP {http}"
    if http == 0:
        return EndpointStatus.UNREACHABLE, prof_result.error_summary or "connection error"
    return EndpointStatus.UNKNOWN, prof_result.error_summary or f"HTTP {http}"


# ---------------------------------------------------------------------------
# LLMRouter
# ---------------------------------------------------------------------------

class LLMRouter:
    """Unified LLM routing with professionalize → Ollama fallback.

    All methods return ``CallResult`` — never raise on network/parse errors.
    """

    def __init__(self, registry_path: Path | None = None, *, _http_client: Any = None):
        self._registry = _load_registry(registry_path)
        self._providers = _sorted_providers(self._registry)
        self._ollama_models: list[str] | None = None
        self._http_client = _http_client

    # -- Ollama discovery ---------------------------------------------------

    def discover_ollama_models(self) -> list[str]:
        """Discover installed Ollama models via /api/tags.

        Returns list of exact model names (e.g. 'llama3.2:latest') ordered by
        preferred_models priority. Cached per router instance.
        """
        if self._ollama_models is not None:
            return self._ollama_models

        self._ollama_models = []
        ollama_cfg = self._registry["providers"].get("ollama")
        if not ollama_cfg:
            return self._ollama_models

        base_url = ollama_cfg.get("base_url", "http://localhost:11434/v1")
        # /api/tags is Ollama-native (not OpenAI-compat), so strip /v1
        tags_url = base_url.replace("/v1", "").rstrip("/") + "/api/tags"

        if requests is None:
            return self._ollama_models

        try:
            resp = requests.get(tags_url, timeout=5)
            if resp.status_code != 200:
                log.warning("Ollama /api/tags returned HTTP %d", resp.status_code)
                return self._ollama_models
            data = resp.json()
        except Exception as exc:
            log.debug("Ollama discovery failed: %s", exc)
            return self._ollama_models

        installed = [m.get("name", "") for m in data.get("models", []) if m.get("name")]
        preferred = ollama_cfg.get("preferred_models", [])

        # Two-pass matching: exact then base-name
        matched: list[str] = []
        remaining: list[str] = list(installed)

        for pref in preferred:
            for inst in remaining[:]:
                base_name = inst.split(":")[0] if ":" in inst else inst
                if inst == pref or base_name == pref:
                    matched.append(inst)
                    remaining.remove(inst)
                    break

        # Append non-preferred models sorted by size desc (if available)
        self._ollama_models = matched + sorted(
            remaining,
            key=lambda n: next(
                (m.get("size", 0) for m in data.get("models", []) if m.get("name") == n), 0
            ),
            reverse=True,
        )
        log.info("Ollama discovery: %d models found, %d preferred-matched",
                 len(installed), len(matched))
        return self._ollama_models

    def _try_ollama_alternative_models(
        self, provider: dict, chat_cfg: dict, body: dict, headers: dict,
        timeout: float, *, json_extract: bool, json_array: bool,
    ) -> CallResult | None:
        """Try alternative Ollama models after a 404 (model missing).

        Returns CallResult on success, None if all alternatives fail.
        """
        discovered = self.discover_ollama_models()
        if not discovered:
            return None

        preferred = provider.get("preferred_models", [])
        candidates = [m for m in discovered if m.split(":")[0] in preferred or m in preferred]
        original = chat_cfg.get("model", "")
        candidates = [m for m in candidates if m != original and m.split(":")[0] != original]

        for alt_model in candidates:
            log.info("Ollama: trying alternative model %s", alt_model)
            alt_body = {**body, "model": alt_model}
            url = provider["base_url"].rstrip("/") + chat_cfg["endpoint"]
            start = time.monotonic()
            try:
                resp = requests.post(url, json=alt_body, headers=headers, timeout=timeout)
                elapsed = (time.monotonic() - start) * 1000
            except Exception:
                continue

            if resp.status_code == 404:
                continue
            if resp.status_code != 200:
                continue

            try:
                content = resp.json()["choices"][0]["message"]["content"]
                if content is None:
                    raise ValueError("content is null")
            except (KeyError, IndexError, json.JSONDecodeError, ValueError):
                continue

            if not json_extract:
                return CallResult(
                    provider="ollama", endpoint=url, model=alt_model,
                    status=EndpointStatus.OK,
                    data=content, http_status=200, latency_ms=elapsed,
                )

            if json_array:
                pattern = r"(\[.*\]|\{.*\})"
            else:
                pattern = r"\{.*\}"
            m = re.search(pattern, content, re.DOTALL)
            if not m:
                continue
            try:
                parsed = json.loads(m.group(1) if json_array else m.group())
            except json.JSONDecodeError:
                continue

            return CallResult(
                provider="ollama", endpoint=url, model=alt_model,
                status=EndpointStatus.OK,
                data=parsed, http_status=200, latency_ms=elapsed,
            )

        return None

    # -- Chat completions ---------------------------------------------------

    def call_chat(
        self,
        prompt_system: str,
        prompt_user: str,
        *,
        temperature: float | None = None,
        max_tokens: int | None = None,
        timeout: float | None = None,
        json_extract: bool = True,
        json_array: bool = False,
    ) -> CallResult:
        """Call chat completions, trying providers in priority order.

        Args:
            prompt_system: System prompt.
            prompt_user: User prompt.
            temperature: Override default temperature from registry.
            max_tokens: Override default max_tokens from registry.
            timeout: Override default timeout from registry.
            json_extract: If True, extract JSON from response content.
            json_array: If True, also accept JSON arrays (not just objects).

        Returns:
            CallResult with ``data`` set to parsed JSON (dict/list) or raw
            string content, depending on json_extract.
        """
        if requests is None and not _PROF_CLIENT_AVAILABLE:
            return CallResult(
                status=EndpointStatus.NOT_CONFIGURED,
                error="requests library not installed",
            )

        first_result: CallResult | None = None
        fallback_artifact = ""
        accumulated_events: list = []

        for name, provider in self._providers:
            api_key = self._get_api_key(provider)
            if api_key is None:
                # api_key_env is set but env var is empty → skip
                if first_result is None:
                    first_result = CallResult(
                        provider=name,
                        status=EndpointStatus.NOT_CONFIGURED,
                        error=f"{provider.get('api_key_env', '')} not set",
                    )
                log.warning(
                    "%s: not_configured — %s not set",
                    name, provider.get("api_key_env", ""),
                )
                continue

            chat_cfg = provider.get("chat", {})
            url = provider["base_url"].rstrip("/") + chat_cfg["endpoint"]
            model = chat_cfg["model"]
            t = timeout if timeout is not None else chat_cfg.get("default_timeout", 90)
            temp = temperature if temperature is not None else chat_cfg.get("default_temperature", 0.0)
            mt = max_tokens if max_tokens is not None else chat_cfg.get("default_max_tokens")

            # -------------------------------------------------------------- #
            # ProfessionalizeClient branch (CS-001)                          #
            # -------------------------------------------------------------- #
            if name == "professionalize" and _PROF_CLIENT_AVAILABLE:
                client = self._build_prof_client(provider, call_site_id="CS-001", timeout=t)
                prof_result = client.chat(
                    messages=[
                        {"role": "system", "content": prompt_system},
                        {"role": "user", "content": prompt_user},
                    ],
                    model=model,
                    temperature=temp,
                    max_tokens=mt,
                )
                accumulated_events.append(prof_result.event)
                ep_status, err_str = _map_prof_status(prof_result)

                if not prof_result.ok:
                    log.warning("%s: %s — %s", name, ep_status.value, url)
                    if first_result is None:
                        first_result = CallResult(
                            provider=name, endpoint=url, model=model,
                            status=ep_status,
                            http_status=prof_result.http_status or 0,
                            latency_ms=float(prof_result.latency_ms or 0),
                            error=err_str,
                            token_usage=0,
                            api_calls_count=prof_result.api_calls_count_delta,
                            metrics_events=list(accumulated_events),
                        )
                    continue

                content = prof_result.content or ""
                elapsed = float(prof_result.latency_ms or 0)
                token_usage_val = prof_result.total_tokens
                api_calls_val = prof_result.api_calls_count_delta

            else:
                # ---------------------------------------------------------- #
                # requests.post transport (ollama or professionalize unavail.)#
                # ---------------------------------------------------------- #
                if requests is None:
                    if first_result is None:
                        first_result = CallResult(
                            provider=name,
                            status=EndpointStatus.NOT_CONFIGURED,
                            error="requests library not installed",
                        )
                    continue

                headers = {"Content-Type": "application/json"}
                if api_key:
                    headers["Authorization"] = f"Bearer {api_key}"

                body: dict[str, Any] = {
                    "model": model,
                    "messages": [
                        {"role": "system", "content": prompt_system},
                        {"role": "user", "content": prompt_user},
                    ],
                    "temperature": temp,
                }
                if mt:
                    body["max_tokens"] = mt

                start = time.monotonic()
                try:
                    resp = requests.post(url, json=body, headers=headers, timeout=t)
                    elapsed = (time.monotonic() - start) * 1000
                except requests.exceptions.Timeout:
                    elapsed = (time.monotonic() - start) * 1000
                    log.warning("%s: timeout after %.0fms — %s", name, elapsed, url)
                    if first_result is None:
                        first_result = CallResult(
                            provider=name, endpoint=url, model=model,
                            status=EndpointStatus.UNREACHABLE,
                            latency_ms=elapsed, error="timeout",
                        )
                    continue
                except Exception as exc:
                    elapsed = (time.monotonic() - start) * 1000
                    log.warning("%s: unreachable — %s: %s", name, url, exc)
                    if first_result is None:
                        first_result = CallResult(
                            provider=name, endpoint=url, model=model,
                            status=EndpointStatus.UNREACHABLE,
                            latency_ms=elapsed, error=str(exc),
                        )
                    continue

                if resp.status_code in (401, 403):
                    log.warning("%s: auth_failed (HTTP %d) — %s", name, resp.status_code, url)
                    if first_result is None:
                        first_result = CallResult(
                            provider=name, endpoint=url, model=model,
                            status=EndpointStatus.AUTH_FAILED,
                            http_status=resp.status_code, latency_ms=elapsed,
                            error=f"HTTP {resp.status_code}",
                        )
                    continue

                if resp.status_code == 404 and name == "ollama":
                    log.warning("%s: model_missing (HTTP 404) — %s", name, model)
                    alt_result = self._try_ollama_alternative_models(
                        provider, chat_cfg, body, headers, t,
                        json_extract=json_extract, json_array=json_array,
                    )
                    if alt_result is not None:
                        if first_result is not None:
                            alt_result.fallback_artifact = self._write_fallback_artifact(
                                alt_result.provider, first_result, "chat"
                            )
                        alt_result.metrics_events = list(accumulated_events)
                        return alt_result
                    if first_result is None:
                        first_result = CallResult(
                            provider=name, endpoint=url, model=model,
                            status=EndpointStatus.MODEL_MISSING,
                            http_status=404, latency_ms=elapsed,
                            error=f"Model '{model}' not found, no alternatives available",
                        )
                    continue

                if resp.status_code != 200:
                    log.warning(
                        "%s: HTTP %d — %s: %s",
                        name, resp.status_code, url, resp.text[:200],
                    )
                    if first_result is None:
                        first_result = CallResult(
                            provider=name, endpoint=url, model=model,
                            status=EndpointStatus.UNKNOWN,
                            http_status=resp.status_code, latency_ms=elapsed,
                            error=f"HTTP {resp.status_code}: {resp.text[:200]}",
                        )
                    continue

                # HTTP 200 — parse response
                try:
                    content = resp.json()["choices"][0]["message"]["content"]
                    if content is None:
                        raise ValueError("content is null")
                except (KeyError, IndexError, json.JSONDecodeError, ValueError) as exc:
                    log.warning("%s: parse_failed — %s", name, exc)
                    if first_result is None:
                        first_result = CallResult(
                            provider=name, endpoint=url, model=model,
                            status=EndpointStatus.PARSE_FAILED,
                            http_status=200, latency_ms=elapsed,
                            error=f"Response parse failed: {exc}",
                        )
                    continue

                token_usage_val = 0
                api_calls_val = 0

            # -------------------------------------------------------------- #
            # Shared: JSON extraction + success return                       #
            # -------------------------------------------------------------- #
            if not json_extract:
                # Write fallback artifact if this is a secondary provider
                if first_result is not None:
                    fallback_artifact = self._write_fallback_artifact(
                        name, first_result, "chat"
                    )
                return CallResult(
                    provider=name, endpoint=url, model=model,
                    status=EndpointStatus.OK,
                    data=content, http_status=200, latency_ms=elapsed,
                    fallback_artifact=fallback_artifact,
                    token_usage=token_usage_val,
                    api_calls_count=api_calls_val,
                    metrics_events=list(accumulated_events),
                )

            # Extract JSON from content
            if json_array:
                pattern = r"(\[.*\]|\{.*\})"
            else:
                pattern = r"\{.*\}"
            m = re.search(pattern, content, re.DOTALL)
            if not m:
                log.warning("%s: parse_failed — no JSON found in response", name)
                if first_result is None:
                    first_result = CallResult(
                        provider=name, endpoint=url, model=model,
                        status=EndpointStatus.PARSE_FAILED,
                        http_status=200, latency_ms=elapsed,
                        error="No JSON found in response",
                    )
                continue

            try:
                parsed = json.loads(m.group(1) if json_array else m.group())
            except json.JSONDecodeError as exc:
                log.warning("%s: parse_failed — invalid JSON: %s", name, exc)
                if first_result is None:
                    first_result = CallResult(
                        provider=name, endpoint=url, model=model,
                        status=EndpointStatus.PARSE_FAILED,
                        http_status=200, latency_ms=elapsed,
                        error=f"Invalid JSON: {exc}",
                    )
                continue

            # Success — write fallback artifact if we fell back
            if first_result is not None:
                fallback_artifact = self._write_fallback_artifact(
                    name, first_result, "chat"
                )
            return CallResult(
                provider=name, endpoint=url, model=model,
                status=EndpointStatus.OK,
                data=parsed, http_status=200, latency_ms=elapsed,
                fallback_artifact=fallback_artifact,
                token_usage=token_usage_val,
                api_calls_count=api_calls_val,
                metrics_events=list(accumulated_events),
            )

        # All providers failed
        if first_result is not None:
            first_result.metrics_events = list(accumulated_events)
            log.error(
                "All LLM providers failed. First failure: %s (%s)",
                first_result.provider, first_result.error,
            )
            return first_result

        return CallResult(
            status=EndpointStatus.NOT_CONFIGURED,
            error="No providers available",
            metrics_events=list(accumulated_events),
        )

    # -- Embeddings ---------------------------------------------------------

    def call_embeddings(
        self,
        texts: list[str],
        *,
        timeout: float | None = None,
        batch_size: int = 32,
    ) -> CallResult:
        """Call embeddings endpoint, trying providers in priority order.

        Returns CallResult with ``data`` set to list[list[float]] on success.
        Validates returned dimensions against registry ``embed_dimensions``.
        """
        if requests is None and not _PROF_CLIENT_AVAILABLE:
            return CallResult(
                status=EndpointStatus.NOT_CONFIGURED,
                error="requests library not installed",
            )

        first_result: CallResult | None = None
        fallback_artifact = ""
        accumulated_events: list = []

        for name, provider in self._providers:
            embed_cfg = provider.get("embeddings")
            if not embed_cfg:
                continue

            api_key = self._get_api_key(provider)
            if api_key is None:
                if first_result is None:
                    first_result = CallResult(
                        provider=name,
                        status=EndpointStatus.NOT_CONFIGURED,
                        error=f"{provider.get('api_key_env', '')} not set",
                    )
                log.warning(
                    "%s: not_configured — %s not set",
                    name, provider.get("api_key_env", ""),
                )
                continue

            url = provider["base_url"].rstrip("/") + embed_cfg["endpoint"]
            model = embed_cfg["model"]
            t = timeout if timeout is not None else embed_cfg.get("default_timeout", 30)
            expected_dims = embed_cfg.get("embed_dimensions")

            # -------------------------------------------------------------- #
            # ProfessionalizeClient branch (CS-002)                          #
            # -------------------------------------------------------------- #
            if name == "professionalize" and _PROF_CLIENT_AVAILABLE:
                client = self._build_prof_client(provider, call_site_id="CS-002", timeout=t)
                all_vectors: list[list[float]] = []
                failed = False
                total_start = time.monotonic()
                prof_total_tokens = 0
                prof_api_calls = 0

                for i in range(0, len(texts), batch_size):
                    batch = texts[i : i + batch_size]
                    prof_result = client.embed(texts=batch)
                    accumulated_events.append(prof_result.event)
                    prof_total_tokens += prof_result.total_tokens
                    prof_api_calls += prof_result.api_calls_count_delta

                    ep_status, err_str = _map_prof_status(prof_result)
                    if not prof_result.ok:
                        log.warning("%s: %s — %s", name, ep_status.value, url)
                        if first_result is None:
                            first_result = CallResult(
                                provider=name, endpoint=url, model=model,
                                status=ep_status,
                                http_status=prof_result.http_status or 0,
                                latency_ms=float(prof_result.latency_ms or 0),
                                error=err_str,
                                token_usage=prof_total_tokens,
                                api_calls_count=prof_api_calls,
                                metrics_events=list(accumulated_events),
                            )
                        failed = True
                        break

                    try:
                        items = sorted(
                            prof_result.data or [],
                            key=lambda x: x.get("index", 0) if isinstance(x, dict) else 0,
                        )
                        for item in items:
                            all_vectors.append(item["embedding"])
                    except (KeyError, TypeError) as exc:
                        log.warning("%s: parse_failed — %s", name, exc)
                        if first_result is None:
                            first_result = CallResult(
                                provider=name, endpoint=url, model=model,
                                status=EndpointStatus.PARSE_FAILED,
                                http_status=200,
                                latency_ms=float(prof_result.latency_ms or 0),
                                error=f"Embedding parse failed: {exc}",
                                token_usage=prof_total_tokens,
                                api_calls_count=prof_api_calls,
                                metrics_events=list(accumulated_events),
                            )
                        failed = True
                        break

                if failed:
                    continue

                total_elapsed = (time.monotonic() - total_start) * 1000

                # Dimension validation
                if expected_dims and all_vectors:
                    actual_dims = len(all_vectors[0])
                    if actual_dims != expected_dims:
                        log.warning(
                            "%s: dimension mismatch — expected %d, got %d",
                            name, expected_dims, actual_dims,
                        )
                        if first_result is None:
                            first_result = CallResult(
                                provider=name, endpoint=url, model=model,
                                status=EndpointStatus.PARSE_FAILED,
                                http_status=200, latency_ms=total_elapsed,
                                error=f"Dimension mismatch: expected {expected_dims}, got {actual_dims}",
                                token_usage=prof_total_tokens,
                                api_calls_count=prof_api_calls,
                                metrics_events=list(accumulated_events),
                            )
                        continue

                # Success
                if first_result is not None:
                    fallback_artifact = self._write_fallback_artifact(
                        name, first_result, "embeddings"
                    )
                return CallResult(
                    provider=name, endpoint=url, model=model,
                    status=EndpointStatus.OK,
                    data=all_vectors, http_status=200, latency_ms=total_elapsed,
                    fallback_artifact=fallback_artifact,
                    token_usage=prof_total_tokens,
                    api_calls_count=prof_api_calls,
                    metrics_events=list(accumulated_events),
                )

            else:
                # ---------------------------------------------------------- #
                # requests.post batching (ollama or professionalize unavail.) #
                # ---------------------------------------------------------- #
                if requests is None:
                    if first_result is None:
                        first_result = CallResult(
                            provider=name,
                            status=EndpointStatus.NOT_CONFIGURED,
                            error="requests library not installed",
                        )
                    continue

                headers = {"Content-Type": "application/json"}
                if api_key:
                    headers["Authorization"] = f"Bearer {api_key}"

                all_vectors_req: list[list[float]] = []
                failed_req = False
                total_start_req = time.monotonic()

                for i in range(0, len(texts), batch_size):
                    batch = texts[i : i + batch_size]
                    start = time.monotonic()
                    try:
                        resp = requests.post(
                            url,
                            json={"model": model, "input": batch},
                            headers=headers,
                            timeout=t,
                        )
                        elapsed = (time.monotonic() - start) * 1000
                    except requests.exceptions.Timeout:
                        elapsed = (time.monotonic() - start) * 1000
                        log.warning("%s: timeout after %.0fms — %s", name, elapsed, url)
                        if first_result is None:
                            first_result = CallResult(
                                provider=name, endpoint=url, model=model,
                                status=EndpointStatus.UNREACHABLE,
                                latency_ms=elapsed, error="timeout",
                            )
                        failed_req = True
                        break
                    except Exception as exc:
                        elapsed = (time.monotonic() - start) * 1000
                        log.warning("%s: unreachable — %s: %s", name, url, exc)
                        if first_result is None:
                            first_result = CallResult(
                                provider=name, endpoint=url, model=model,
                                status=EndpointStatus.UNREACHABLE,
                                latency_ms=elapsed, error=str(exc),
                            )
                        failed_req = True
                        break

                    if resp.status_code in (401, 403):
                        log.warning(
                            "%s: auth_failed (HTTP %d) — %s",
                            name, resp.status_code, url,
                        )
                        if first_result is None:
                            first_result = CallResult(
                                provider=name, endpoint=url, model=model,
                                status=EndpointStatus.AUTH_FAILED,
                                http_status=resp.status_code, latency_ms=elapsed,
                                error=f"HTTP {resp.status_code}",
                            )
                        failed_req = True
                        break

                    if resp.status_code != 200:
                        log.warning(
                            "%s: HTTP %d — %s: %s",
                            name, resp.status_code, url, resp.text[:200],
                        )
                        if first_result is None:
                            first_result = CallResult(
                                provider=name, endpoint=url, model=model,
                                status=EndpointStatus.UNKNOWN,
                                http_status=resp.status_code, latency_ms=elapsed,
                                error=f"HTTP {resp.status_code}: {resp.text[:200]}",
                            )
                        failed_req = True
                        break

                    try:
                        data = resp.json()
                        items = sorted(
                            data.get("data", []), key=lambda x: x.get("index", 0)
                        )
                        for item in items:
                            all_vectors_req.append(item["embedding"])
                    except (KeyError, json.JSONDecodeError) as exc:
                        log.warning("%s: parse_failed — %s", name, exc)
                        if first_result is None:
                            first_result = CallResult(
                                provider=name, endpoint=url, model=model,
                                status=EndpointStatus.PARSE_FAILED,
                                http_status=200, latency_ms=elapsed,
                                error=f"Response parse failed: {exc}",
                            )
                        failed_req = True
                        break

                if failed_req:
                    continue

                total_elapsed_req = (time.monotonic() - total_start_req) * 1000

                # Dimension validation
                if expected_dims and all_vectors_req:
                    actual_dims = len(all_vectors_req[0])
                    if actual_dims != expected_dims:
                        log.warning(
                            "%s: dimension mismatch — expected %d, got %d",
                            name, expected_dims, actual_dims,
                        )
                        if first_result is None:
                            first_result = CallResult(
                                provider=name, endpoint=url, model=model,
                                status=EndpointStatus.PARSE_FAILED,
                                http_status=200, latency_ms=total_elapsed_req,
                                error=f"Dimension mismatch: expected {expected_dims}, got {actual_dims}",
                            )
                        continue

                # Success
                if first_result is not None:
                    fallback_artifact = self._write_fallback_artifact(
                        name, first_result, "embeddings"
                    )
                return CallResult(
                    provider=name, endpoint=url, model=model,
                    status=EndpointStatus.OK,
                    data=all_vectors_req, http_status=200, latency_ms=total_elapsed_req,
                    fallback_artifact=fallback_artifact,
                    metrics_events=list(accumulated_events),
                )

        # All providers failed
        if first_result is not None:
            first_result.metrics_events = list(accumulated_events)
            log.error(
                "All embedding providers failed. First failure: %s (%s)",
                first_result.provider, first_result.error,
            )
            return first_result

        return CallResult(
            status=EndpointStatus.NOT_CONFIGURED,
            error="No embedding providers available",
            metrics_events=list(accumulated_events),
        )

    # -- Probe --------------------------------------------------------------

    def probe(self, provider_filter: str | None = None) -> dict[str, dict]:
        """Probe each provider's chat endpoint with a trivial request.

        Returns dict mapping provider name to status info.
        """
        results: dict[str, dict] = {}

        for name, provider in self._providers:
            if provider_filter and name != provider_filter:
                continue

            api_key = self._get_api_key(provider)
            if api_key is None:
                results[name] = {
                    "status": EndpointStatus.NOT_CONFIGURED.value,
                    "error": f"{provider.get('api_key_env', '')} not set",
                }
                continue

            if requests is None:
                results[name] = {
                    "status": EndpointStatus.NOT_CONFIGURED.value,
                    "error": "requests library not installed",
                }
                continue

            chat_cfg = provider.get("chat", {})
            url = provider["base_url"].rstrip("/") + chat_cfg["endpoint"]
            model = chat_cfg["model"]

            headers = {"Content-Type": "application/json"}
            if api_key:
                headers["Authorization"] = f"Bearer {api_key}"

            start = time.monotonic()
            try:
                resp = requests.post(
                    url,
                    json={
                        "model": model,
                        "messages": [{"role": "user", "content": "Reply with OK"}],
                        "temperature": 0.0,
                        "max_tokens": 5,
                    },
                    headers=headers,
                    timeout=15,
                )
                elapsed = (time.monotonic() - start) * 1000
            except requests.exceptions.Timeout:
                elapsed = (time.monotonic() - start) * 1000
                results[name] = {
                    "status": EndpointStatus.UNREACHABLE.value,
                    "error": "timeout",
                    "latency_ms": round(elapsed, 1),
                }
                continue
            except Exception as exc:
                elapsed = (time.monotonic() - start) * 1000
                results[name] = {
                    "status": EndpointStatus.UNREACHABLE.value,
                    "error": str(exc),
                    "latency_ms": round(elapsed, 1),
                }
                continue

            if resp.status_code == 200:
                results[name] = {
                    "status": EndpointStatus.OK.value,
                    "latency_ms": round(elapsed, 1),
                    "model": model,
                }
            elif resp.status_code in (401, 403):
                results[name] = {
                    "status": EndpointStatus.AUTH_FAILED.value,
                    "http_status": resp.status_code,
                    "latency_ms": round(elapsed, 1),
                }
            elif resp.status_code == 404 and name == "ollama":
                discovered = self.discover_ollama_models()
                if discovered:
                    results[name] = {
                        "status": EndpointStatus.OK.value,
                        "latency_ms": round(elapsed, 1),
                        "model": f"{model} (missing), available: {discovered[0]}",
                    }
                else:
                    results[name] = {
                        "status": EndpointStatus.MODEL_MISSING.value,
                        "http_status": 404,
                        "latency_ms": round(elapsed, 1),
                    }
            else:
                results[name] = {
                    "status": f"http_{resp.status_code}",
                    "http_status": resp.status_code,
                    "latency_ms": round(elapsed, 1),
                }

        return results

    # -- Helpers ------------------------------------------------------------

    @staticmethod
    def _get_api_key(provider: dict) -> str | None:
        """Return API key for provider.

        Returns:
            - "" (empty string) if no api_key_env configured (no key needed)
            - None if api_key_env is configured but env var is empty/absent
            - The key string otherwise
        """
        env_var = provider.get("api_key_env")
        if not env_var:
            return ""  # No key required (e.g. Ollama)
        key = os.environ.get(env_var, "").strip()
        if not key:
            return None
        return key

    def _build_prof_client(
        self, provider: dict, *, call_site_id: str, timeout: float
    ) -> Any:
        """Build ProfessionalizeClient from provider config for metrics-aware transport."""
        chat_cfg = provider.get("chat", {})
        embed_cfg = provider.get("embeddings", {})
        raw_key = self._get_api_key(provider)
        return ProfessionalizeClient(
            base_url=provider["base_url"],
            api_key=raw_key if raw_key else None,
            default_chat_model=chat_cfg.get("model"),
            default_embedding_model=embed_cfg.get("model"),
            timeout=timeout,
            http_client=self._http_client,
            call_site_id=call_site_id,
        )

    @staticmethod
    def _write_fallback_artifact(
        fallback_provider: str,
        first_failure: CallResult,
        call_type: str,
    ) -> str:
        """Write a fallback artifact to reports/ when switching providers.

        Returns the artifact path, or empty string on write failure.
        """
        reports_dir = Path(__file__).resolve().parent.parent.parent.parent.parent / "reports"
        try:
            reports_dir.mkdir(parents=True, exist_ok=True)
            artifact_name = (
                f"llm_fallback_{call_type}_{first_failure.provider}"
                f"_to_{fallback_provider}_{int(time.time())}.json"
            )
            artifact_path = reports_dir / artifact_name
            artifact_data = {
                "event": "llm_fallback",
                "call_type": call_type,
                "primary_provider": first_failure.provider,
                "primary_status": first_failure.status.value,
                "primary_error": first_failure.error,
                "primary_http_status": first_failure.http_status,
                "fallback_provider": fallback_provider,
                "timestamp": time.time(),
            }
            artifact_path.write_text(
                json.dumps(artifact_data, indent=2), encoding="utf-8"
            )
            log.warning(
                "Fell back from %s (%s) to %s — artifact: %s",
                first_failure.provider, first_failure.status.value,
                fallback_provider, artifact_path,
            )
            return str(artifact_path)
        except OSError as exc:
            log.warning("Could not write fallback artifact: %s", exc)
            return ""

    # -- Registry access ----------------------------------------------------

    def get_provider_config(self, name: str) -> dict | None:
        """Return raw provider config dict by name."""
        return self._registry["providers"].get(name)

    def get_embed_dimensions(self, provider_name: str) -> int | None:
        """Return expected embedding dimensions for a provider."""
        cfg = self.get_provider_config(provider_name)
        if cfg and cfg.get("embeddings"):
            return cfg["embeddings"].get("embed_dimensions")
        return None


# ---------------------------------------------------------------------------
# CLI: --probe
# ---------------------------------------------------------------------------

def main():
    parser = argparse.ArgumentParser(description="LLM Router — probe endpoints")
    parser.add_argument(
        "--probe", action="store_true",
        help="Probe all providers and print status",
    )
    parser.add_argument(
        "--provider", type=str, default=None,
        help="Probe only this provider (e.g. 'professionalize' or 'ollama')",
    )
    args = parser.parse_args()

    if not args.probe:
        parser.print_help()
        sys.exit(0)

    try:
        router = LLMRouter()
    except RuntimeError as exc:
        print(f"ERROR: {exc}", file=sys.stderr)
        sys.exit(1)

    results = router.probe(provider_filter=args.provider)

    # Write probe artifact
    reports_dir = Path(__file__).resolve().parent.parent.parent.parent.parent / "reports"
    try:
        reports_dir.mkdir(parents=True, exist_ok=True)
        artifact = reports_dir / f"llm_probe_{int(time.time())}.json"
        artifact.write_text(json.dumps(results, indent=2), encoding="utf-8")
        print(f"Probe artifact: {artifact}")
    except OSError as exc:
        print(f"WARNING: Could not write probe artifact: {exc}", file=sys.stderr)

    for name, info in results.items():
        status = info.get("status", "unknown")
        latency = info.get("latency_ms", "")
        lat_str = f" ({latency:.0f}ms)" if latency else ""
        print(f"  {name}: {status}{lat_str}")

    sys.exit(0)


if __name__ == "__main__":
    main()
