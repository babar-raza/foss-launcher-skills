#!/usr/bin/env python3
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
import hashlib
import json
import logging
import os
import re
import sys
import time
import uuid
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

try:
    import json_repair as _json_repair
    _HAS_JSON_REPAIR = True
except ImportError:
    _HAS_JSON_REPAIR = False

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
    CONFIG_INVALID = "config_invalid"
    CONTRACT_MISMATCH = "contract_mismatch"
    UNKNOWN = "unknown"


# ---------------------------------------------------------------------------
# Public routing dataclasses
# ---------------------------------------------------------------------------

@dataclass(frozen=True)
class LLMCallContext:
    consumer_id: str
    run_id: str
    job_type: str
    work_slice_id: str

    @classmethod
    def create(
        cls, consumer_id: str, job_type: str, work_slice_id: str
    ) -> "LLMCallContext":
        return cls(consumer_id, str(uuid.uuid4()), job_type, work_slice_id)


@dataclass(frozen=True)
class EmbeddingProfile:
    profile_id: str
    provider: str
    model: str
    dimensions: int
    config_digest: str


@dataclass(frozen=True)
class ProviderAttempt:
    provider: str
    endpoint: str
    model: str
    status: EndpointStatus
    latency_ms: float
    credential_env_name: str | None = None
    observed_dimensions: int | None = None


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
    attempts: list[ProviderAttempt] = field(default_factory=list)
    config_digest: str = ""
    embedding_profile: EmbeddingProfile | None = None


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
    if data.get("schema_version", 2) != 2:
        raise RuntimeError(f"Invalid LLM registry (schema_version must be 2): {p}")
    for name, provider in data["providers"].items():
        if not isinstance(provider.get("base_url"), str):
            raise RuntimeError(f"Invalid LLM registry ({name}.base_url)")
        aliases = provider.get("credential_aliases", [])
        if aliases is not None and not isinstance(aliases, list):
            raise RuntimeError(f"Invalid LLM registry ({name}.credential_aliases)")
        if any(not isinstance(alias, str) or not alias.strip() for alias in aliases or []):
            raise RuntimeError(f"Invalid LLM registry ({name}.credential_aliases)")
        retry = provider.get("retry", {})
        if retry is not None and not isinstance(retry, dict):
            raise RuntimeError(f"Invalid LLM registry ({name}.retry)")
        retry = retry or {}
        max_attempts = retry.get("max_attempts", 1)
        retry_statuses = retry.get("retry_statuses", [])
        if (
            not isinstance(max_attempts, int)
            or isinstance(max_attempts, bool)
            or max_attempts < 1
        ):
            raise RuntimeError(f"Invalid LLM registry ({name}.retry.max_attempts)")
        if (
            not isinstance(retry_statuses, list)
            or any(
                not isinstance(status, int)
                or isinstance(status, bool)
                or status < 100
                or status > 599
                for status in retry_statuses
            )
        ):
            raise RuntimeError(f"Invalid LLM registry ({name}.retry.retry_statuses)")
        for operation in ("chat", "embeddings"):
            cfg = provider.get(operation)
            if cfg and (not cfg.get("endpoint") or not cfg.get("model")):
                raise RuntimeError(f"Invalid LLM registry ({name}.{operation})")
        ecfg = provider.get("embeddings")
        if ecfg and (
            not isinstance(ecfg.get("embed_dimensions"), int)
            or ecfg["embed_dimensions"] <= 0
        ):
            raise RuntimeError(f"Invalid LLM registry ({name}.embeddings.embed_dimensions)")
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
    if 200 <= http < 300:
        return EndpointStatus.PARSE_FAILED, (
            prof_result.error_summary or "successful HTTP response violated response schema"
        )
    return EndpointStatus.UNKNOWN, prof_result.error_summary or f"HTTP {http}"


def _provider_attempts(
    result: Any,
    provider: str,
    endpoint: str,
    model: str,
    observed_dimensions: int | None = None,
    expected_dimensions: int | None = None,
) -> list[ProviderAttempt]:
    """Convert transport-safe credential attempts to the public typed history."""
    attempts: list[ProviderAttempt] = []
    for item in result.credential_attempts or []:
        http = item.get("http_status") or 0
        if http in (401, 403):
            status = EndpointStatus.AUTH_FAILED
        elif 200 <= http < 300:
            status = (
                EndpointStatus.OK
                if result.ok
                else EndpointStatus.PARSE_FAILED
            )
            if (
                observed_dimensions is not None
                and expected_dimensions is not None
                and observed_dimensions != expected_dimensions
            ):
                status = EndpointStatus.CONTRACT_MISMATCH
        elif http == 0:
            status = EndpointStatus.UNREACHABLE
        else:
            status = EndpointStatus.UNKNOWN
        attempts.append(ProviderAttempt(
            provider=provider,
            endpoint=endpoint,
            model=model,
            status=status,
            latency_ms=float(item.get("latency_ms") or 0),
            credential_env_name=item.get("credential_env_name"),
            observed_dimensions=observed_dimensions,
        ))
    return attempts


def _reclassify_last_attempt(
    attempts: list[ProviderAttempt],
    status: EndpointStatus,
    *,
    observed_dimensions: int | None = None,
) -> None:
    """Update the final transport attempt after router-level schema checks."""
    if not attempts:
        return
    attempt = attempts[-1]
    attempts[-1] = ProviderAttempt(
        provider=attempt.provider,
        endpoint=attempt.endpoint,
        model=attempt.model,
        status=status,
        latency_ms=attempt.latency_ms,
        credential_env_name=attempt.credential_env_name,
        observed_dimensions=(
            observed_dimensions
            if observed_dimensions is not None
            else attempt.observed_dimensions
        ),
    )


# ---------------------------------------------------------------------------
# LLMRouter
# ---------------------------------------------------------------------------

class LLMRouter:
    """Unified LLM routing with professionalize → Ollama fallback.

    All methods return ``CallResult`` — never raise on network/parse errors.
    """

    def __init__(
        self,
        registry_path: Path | None = None,
        *,
        _http_client: Any = None,
        _credential_env: dict[str, str] | None = None,
    ):
        self._registry_path = registry_path or _REGISTRY_PATH
        self._registry = _load_registry(self._registry_path)
        self._providers = _sorted_providers(self._registry)
        self._config_digest = self._digest_registry()
        self._ollama_models: list[str] | None = None
        self._http_client = _http_client
        self._credential_env_override = _credential_env

    def _env_get(self, name: str) -> str:
        """Resolve a credential env var name, honoring the test-only override.

        Names present in ``_credential_env`` (if passed to the constructor)
        are resolved deterministically from that dict, regardless of the
        ambient process environment. Names absent from it fall through to
        the real ``os.environ`` — this lets a test pin the one credential it
        cares about while still layering its own additional env-var patches
        (e.g. a custom ``credential_aliases`` set) around the actual call.
        """
        if self._credential_env_override is not None and name in self._credential_env_override:
            return self._credential_env_override[name]
        return os.environ.get(name, "").strip()

    def _digest_registry(self) -> str:
        return hashlib.sha256(self._registry_path.read_bytes()).hexdigest()

    def _reload_registry(self) -> str | None:
        """Atomically validate and install changed configuration, or fail closed."""
        try:
            digest = hashlib.sha256(self._registry_path.read_bytes()).hexdigest()
            if digest == self._config_digest:
                return None
            registry = _load_registry(self._registry_path)
        except Exception as exc:  # configuration errors are typed, never stale
            return str(exc)
        self._registry = registry
        self._providers = _sorted_providers(registry)
        self._config_digest = digest
        self._ollama_models = None
        return None

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
            data = json.loads(resp.content.decode("utf-8"))
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
            url = self._resolve_base_url(provider) + chat_cfg["endpoint"]
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
                content = json.loads(resp.content.decode("utf-8"))["choices"][0]["message"]["content"]
                if content is None:
                    raise ValueError("content is null")
            except (KeyError, IndexError, json.JSONDecodeError, ValueError, UnicodeDecodeError):
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
        context: LLMCallContext | None = None,
        operation: str = "general_chat",
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
        config_error = self._reload_registry()
        if config_error:
            return CallResult(
                status=EndpointStatus.CONFIG_INVALID,
                error=config_error,
                config_digest=self._config_digest,
            )
        if requests is None and not _PROF_CLIENT_AVAILABLE:
            return CallResult(
                status=EndpointStatus.NOT_CONFIGURED,
                error="requests library not installed",
            )

        first_result: CallResult | None = None
        fallback_artifact = ""
        accumulated_events: list = []
        accumulated_attempts: list[ProviderAttempt] = []

        allowed = set(
            self._registry.get("operation_profiles", {})
            .get(operation, {})
            .get("providers", [name for name, _ in self._providers])
        )
        for name, provider in self._providers:
            if name not in allowed:
                continue
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
            url = self._resolve_base_url(provider) + chat_cfg["endpoint"]
            model = chat_cfg["model"]
            t = timeout if timeout is not None else chat_cfg.get("default_timeout", 90)
            temp = temperature if temperature is not None else chat_cfg.get("default_temperature", 0.0)
            mt = max_tokens if max_tokens is not None else chat_cfg.get("default_max_tokens")

            # -------------------------------------------------------------- #
            # Per-provider attempt loop (max 2 tries on JSON parse failure) #
            # -------------------------------------------------------------- #
            parsed = None
            _parse_attempt = 0
            while _parse_attempt < 2:
                _skip = False  # True → break inner loop; outer loop advances

                # ---------------------------------------------------------- #
                # ProfessionalizeClient branch (CS-001)                      #
                # ---------------------------------------------------------- #
                if name == "professionalize" and _PROF_CLIENT_AVAILABLE:
                    call_site_id = {
                        "seo-recommend": "CS-009",
                        "llm-candidate-enricher": "CS-014",
                    }.get(context.consumer_id if context else "", "CS-001")
                    client = self._build_prof_client(
                        provider, call_site_id=call_site_id, timeout=t, context=context
                    )
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
                    accumulated_attempts.extend(
                        _provider_attempts(prof_result, name, url, model)
                    )
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
                        _skip = True
                    else:
                        content = prof_result.content or ""
                        elapsed = float(prof_result.latency_ms or 0)
                        token_usage_val = prof_result.total_tokens
                        api_calls_val = prof_result.api_calls_count_delta

                else:
                    # -------------------------------------------------------- #
                    # requests.post transport (ollama / professionalize unavail)#
                    # -------------------------------------------------------- #
                    if requests is None:
                        if first_result is None:
                            first_result = CallResult(
                                provider=name,
                                status=EndpointStatus.NOT_CONFIGURED,
                                error="requests library not installed",
                            )
                        _skip = True

                    if not _skip:
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
                            _skip = True
                        except Exception as exc:
                            elapsed = (time.monotonic() - start) * 1000
                            log.warning("%s: unreachable — %s: %s", name, url, exc)
                            if first_result is None:
                                first_result = CallResult(
                                    provider=name, endpoint=url, model=model,
                                    status=EndpointStatus.UNREACHABLE,
                                    latency_ms=elapsed, error=str(exc),
                                )
                            _skip = True

                    if not _skip and resp.status_code in (401, 403):
                        log.warning("%s: auth_failed (HTTP %d) — %s", name, resp.status_code, url)
                        if first_result is None:
                            first_result = CallResult(
                                provider=name, endpoint=url, model=model,
                                status=EndpointStatus.AUTH_FAILED,
                                http_status=resp.status_code, latency_ms=elapsed,
                                error=f"HTTP {resp.status_code}",
                            )
                        _skip = True

                    if not _skip and resp.status_code == 404 and name == "ollama":
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
                        _skip = True

                    if not _skip and resp.status_code != 200:
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
                        _skip = True

                    if not _skip:
                        # HTTP 200 — parse response
                        try:
                            content = json.loads(resp.content.decode("utf-8"))["choices"][0]["message"]["content"]
                            if content is None:
                                raise ValueError("content is null")
                        except (KeyError, IndexError, json.JSONDecodeError, ValueError, UnicodeDecodeError) as exc:
                            log.warning("%s: parse_failed — %s", name, exc)
                            if first_result is None:
                                first_result = CallResult(
                                    provider=name, endpoint=url, model=model,
                                    status=EndpointStatus.PARSE_FAILED,
                                    http_status=200, latency_ms=elapsed,
                                    error=f"Response parse failed: {exc}",
                                )
                            _skip = True

                    if not _skip:
                        token_usage_val = 0
                        api_calls_val = 0

                if _skip:
                    break  # exit inner loop; outer for-loop advances to next provider

                # -------------------------------------------------------------- #
                # Shared: JSON extraction + repair + retry                       #
                # -------------------------------------------------------------- #
                if not json_extract:
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
                        attempts=list(accumulated_attempts),
                        config_digest=self._config_digest,
                    )

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
                    break  # no point retrying; model returned no JSON block

                raw_json_str = m.group(1) if json_array else m.group()
                try:
                    parsed = json.loads(raw_json_str)
                    break  # success — exit inner loop
                except json.JSONDecodeError as exc:
                    # --- Repair pass: try json_repair before spending another HTTP call ---
                    if _HAS_JSON_REPAIR:
                        try:
                            repaired = _json_repair.repair_json(
                                raw_json_str, return_objects=True
                            )
                        except Exception:
                            repaired = None
                        if repaired:
                            log.info(
                                "%s: json_repair succeeded on parse_attempt %d",
                                name, _parse_attempt,
                            )
                            parsed = repaired
                            break  # repaired — exit inner loop as success

                    # --- Retry pass: one more HTTP call to the same provider ---
                    if _parse_attempt == 0:
                        log.info(
                            "%s: parse_failed on attempt 0 (repair unavailable/failed),"
                            " retrying same provider: %s",
                            name, exc,
                        )
                        _parse_attempt += 1
                        continue  # re-enter while loop → new HTTP call

                    # _parse_attempt == 1 also failed — give up on this provider
                    log.warning("%s: parse_failed — invalid JSON: %s", name, exc)
                    if first_result is None:
                        first_result = CallResult(
                            provider=name, endpoint=url, model=model,
                            status=EndpointStatus.PARSE_FAILED,
                            http_status=200, latency_ms=elapsed,
                            error=f"Invalid JSON: {exc}",
                        )
                    break  # exit inner loop; outer for-loop advances to next provider

            # ---------------------------------------------------------------- #
            # End of inner attempt loop                                        #
            # ---------------------------------------------------------------- #
            if parsed is None:
                continue  # outer for-loop: try next provider

            # Success — write fallback artifact if we fell back from another provider
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
                attempts=list(accumulated_attempts),
                config_digest=self._config_digest,
            )

        # All providers failed
        if first_result is not None:
            first_result.metrics_events = list(accumulated_events)
            first_result.attempts = list(accumulated_attempts)
            first_result.config_digest = self._config_digest
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
        context: LLMCallContext | None = None,
        required_profile: EmbeddingProfile | None = None,
        operation: str = "general_embeddings",
    ) -> CallResult:
        """Call embeddings endpoint, trying providers in priority order.

        Returns CallResult with ``data`` set to list[list[float]] on success.
        Validates returned dimensions against registry ``embed_dimensions``.
        """
        config_error = self._reload_registry()
        if config_error:
            return CallResult(
                status=EndpointStatus.CONFIG_INVALID,
                error=config_error,
                config_digest=self._config_digest,
            )
        if requests is None and not _PROF_CLIENT_AVAILABLE:
            return CallResult(
                status=EndpointStatus.NOT_CONFIGURED,
                error="requests library not installed",
            )

        first_result: CallResult | None = None
        fallback_artifact = ""
        accumulated_events: list = []
        accumulated_attempts: list[ProviderAttempt] = []

        allowed = set(
            self._registry.get("operation_profiles", {})
            .get(operation, {})
            .get("providers", [name for name, _ in self._providers])
        )
        for name, provider in self._providers:
            if name not in allowed:
                continue
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

            url = self._resolve_base_url(provider) + embed_cfg["endpoint"]
            model = embed_cfg["model"]
            t = timeout if timeout is not None else embed_cfg.get("default_timeout", 30)
            expected_dims = embed_cfg.get("embed_dimensions")
            profile = EmbeddingProfile(
                profile_id=(
                    f"{name}-{model}-{expected_dims}-{self._config_digest[:12]}"
                ),
                provider=name,
                model=model,
                dimensions=expected_dims,
                config_digest=self._config_digest,
            )
            if required_profile and (
                required_profile.provider != profile.provider
                or required_profile.model != profile.model
                or required_profile.dimensions != profile.dimensions
            ):
                mismatch = CallResult(
                    provider=name, endpoint=url, model=model,
                    status=EndpointStatus.CONTRACT_MISMATCH,
                    error="Stored embedding profile is incompatible with active configuration",
                    config_digest=self._config_digest,
                    embedding_profile=profile,
                )
                if first_result is None:
                    first_result = mismatch
                continue

            # -------------------------------------------------------------- #
            # ProfessionalizeClient branch (CS-002)                          #
            # -------------------------------------------------------------- #
            if name == "professionalize" and _PROF_CLIENT_AVAILABLE:
                call_site_id = {
                    "embed-api-index": "CS-004",
                }.get(context.consumer_id if context else "", "CS-002")
                client = self._build_prof_client(
                    provider, call_site_id=call_site_id, timeout=t, context=context
                )
                all_vectors: list[list[float]] = []
                failed = False
                total_start = time.monotonic()
                prof_total_tokens = 0
                prof_api_calls = 0

                for i in range(0, len(texts), batch_size):
                    batch = texts[i : i + batch_size]
                    # qwen3-embedding-8b supports multiple output dimensions.
                    # Request the registry profile explicitly so a provider-side
                    # default change cannot silently alter the vector contract.
                    prof_result = client.embed(
                        texts=batch,
                        dimensions=expected_dims,
                    )
                    accumulated_events.append(prof_result.event)
                    observed = None
                    if prof_result.data:
                        try:
                            observed = len(prof_result.data[0]["embedding"])
                        except (KeyError, TypeError):
                            observed = None
                    prof_result.event.embedding_profile = profile.profile_id
                    prof_result.event.observed_dimensions = observed
                    prof_result.event.route_outcome = (
                        "contract_mismatch"
                        if observed is not None and observed != expected_dims
                        else prof_result.event.status
                    )
                    accumulated_attempts.extend(
                        _provider_attempts(
                            prof_result,
                            name,
                            url,
                            model,
                            observed,
                            expected_dims,
                        )
                    )
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
                                config_digest=self._config_digest,
                                embedding_profile=profile,
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
                        _reclassify_last_attempt(
                            accumulated_attempts,
                            EndpointStatus.PARSE_FAILED,
                        )
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
                                config_digest=self._config_digest,
                                embedding_profile=profile,
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
                        _reclassify_last_attempt(
                            accumulated_attempts,
                            EndpointStatus.CONTRACT_MISMATCH,
                            observed_dimensions=actual_dims,
                        )
                        if first_result is None:
                            first_result = CallResult(
                                provider=name, endpoint=url, model=model,
                                status=EndpointStatus.CONTRACT_MISMATCH,
                                http_status=200, latency_ms=total_elapsed,
                                error=f"Dimension mismatch: expected {expected_dims}, got {actual_dims}",
                                token_usage=prof_total_tokens,
                                api_calls_count=prof_api_calls,
                                metrics_events=list(accumulated_events),
                                config_digest=self._config_digest,
                                embedding_profile=profile,
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
                    attempts=list(accumulated_attempts),
                    config_digest=self._config_digest,
                    embedding_profile=profile,
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
                        accumulated_attempts.append(ProviderAttempt(
                            provider=name, endpoint=url, model=model,
                            status=EndpointStatus.UNREACHABLE,
                            latency_ms=elapsed,
                        ))
                        log.warning("%s: timeout after %.0fms — %s", name, elapsed, url)
                        if first_result is None:
                            first_result = CallResult(
                                provider=name, endpoint=url, model=model,
                                status=EndpointStatus.UNREACHABLE,
                                latency_ms=elapsed, error="timeout",
                                config_digest=self._config_digest,
                                embedding_profile=profile,
                            )
                        failed_req = True
                        break
                    except Exception as exc:
                        elapsed = (time.monotonic() - start) * 1000
                        accumulated_attempts.append(ProviderAttempt(
                            provider=name, endpoint=url, model=model,
                            status=EndpointStatus.UNREACHABLE,
                            latency_ms=elapsed,
                        ))
                        log.warning("%s: unreachable — %s: %s", name, url, exc)
                        if first_result is None:
                            first_result = CallResult(
                                provider=name, endpoint=url, model=model,
                                status=EndpointStatus.UNREACHABLE,
                                latency_ms=elapsed, error=str(exc),
                                config_digest=self._config_digest,
                                embedding_profile=profile,
                            )
                        failed_req = True
                        break

                    if resp.status_code in (401, 403):
                        accumulated_attempts.append(ProviderAttempt(
                            provider=name, endpoint=url, model=model,
                            status=EndpointStatus.AUTH_FAILED,
                            latency_ms=elapsed,
                        ))
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
                                config_digest=self._config_digest,
                                embedding_profile=profile,
                            )
                        failed_req = True
                        break

                    if resp.status_code != 200:
                        accumulated_attempts.append(ProviderAttempt(
                            provider=name, endpoint=url, model=model,
                            status=EndpointStatus.UNKNOWN,
                            latency_ms=elapsed,
                        ))
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
                                config_digest=self._config_digest,
                                embedding_profile=profile,
                            )
                        failed_req = True
                        break

                    try:
                        data = json.loads(resp.content.decode("utf-8"))
                        items = sorted(
                            data.get("data", []), key=lambda x: x.get("index", 0)
                        )
                        batch_vectors: list[list[float]] = []
                        for item in items:
                            batch_vectors.append(item["embedding"])
                    except (KeyError, TypeError, json.JSONDecodeError, UnicodeDecodeError) as exc:
                        accumulated_attempts.append(ProviderAttempt(
                            provider=name, endpoint=url, model=model,
                            status=EndpointStatus.PARSE_FAILED,
                            latency_ms=elapsed,
                        ))
                        log.warning("%s: parse_failed — %s", name, exc)
                        if first_result is None:
                            first_result = CallResult(
                                provider=name, endpoint=url, model=model,
                                status=EndpointStatus.PARSE_FAILED,
                                http_status=200, latency_ms=elapsed,
                                error=f"Response parse failed: {exc}",
                                config_digest=self._config_digest,
                                embedding_profile=profile,
                            )
                        failed_req = True
                        break

                    observed_dims = len(batch_vectors[0]) if batch_vectors else None
                    if (
                        expected_dims
                        and observed_dims is not None
                        and observed_dims != expected_dims
                    ):
                        accumulated_attempts.append(ProviderAttempt(
                            provider=name, endpoint=url, model=model,
                            status=EndpointStatus.CONTRACT_MISMATCH,
                            latency_ms=elapsed,
                            observed_dimensions=observed_dims,
                        ))
                        log.warning(
                            "%s: dimension mismatch — expected %d, got %d",
                            name, expected_dims, observed_dims,
                        )
                        if first_result is None:
                            first_result = CallResult(
                                provider=name, endpoint=url, model=model,
                                status=EndpointStatus.CONTRACT_MISMATCH,
                                http_status=200, latency_ms=elapsed,
                                error=(
                                    f"Dimension mismatch: expected {expected_dims}, "
                                    f"got {observed_dims}"
                                ),
                                config_digest=self._config_digest,
                                embedding_profile=profile,
                            )
                        failed_req = True
                        break

                    accumulated_attempts.append(ProviderAttempt(
                        provider=name, endpoint=url, model=model,
                        status=EndpointStatus.OK,
                        latency_ms=elapsed,
                        observed_dimensions=observed_dims,
                    ))
                    all_vectors_req.extend(batch_vectors)

                if failed_req:
                    continue

                total_elapsed_req = (time.monotonic() - total_start_req) * 1000

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
                    attempts=list(accumulated_attempts),
                    config_digest=self._config_digest,
                    embedding_profile=profile,
                )

        # All providers failed
        if first_result is not None:
            first_result.metrics_events = list(accumulated_events)
            first_result.attempts = list(accumulated_attempts)
            first_result.config_digest = self._config_digest
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
            url = self._resolve_base_url(provider) + chat_cfg["endpoint"]
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
    def _resolve_base_url(provider: dict) -> str:
        """Return effective base_url for provider.

        If provider has a ``base_url_env`` field and that env var is set,
        the env var value takes precedence over the hardcoded ``base_url``.
        Trailing slashes are stripped for consistent endpoint construction.
        """
        base_url_env = provider.get("base_url_env")
        if base_url_env:
            env_url = os.environ.get(base_url_env, "").strip().rstrip("/")
            if env_url:
                return env_url
        return provider["base_url"].rstrip("/")

    def _get_api_key(self, provider: dict) -> str | None:
        """Return API key for provider.

        Returns:
            - "" (empty string) if no api_key_env configured (no key needed)
            - None if api_key_env is configured but env var is empty/absent
            - The key string otherwise

        Checks api_key_env first; falls back to api_key_env_fallback when
        the primary env var is absent (supports GPT_OSS_API_KEY as fallback
        for PROFESSIONALIZE_API_KEY).
        """
        aliases = provider.get("credential_aliases")
        if aliases:
            for env_var in aliases:
                key = self._env_get(env_var)
                if key:
                    return key
            return None
        env_var = provider.get("api_key_env")
        if not env_var:
            return ""  # No key required (e.g. Ollama)
        key = self._env_get(env_var)
        if not key:
            fallback_var = provider.get("api_key_env_fallback")
            if fallback_var:
                key = self._env_get(fallback_var)
        if not key:
            return None
        return key

    def _get_api_key_candidates(self, provider: dict) -> list[tuple[str, str]]:
        aliases = provider.get("credential_aliases") or []
        if aliases:
            return [
                (name, self._env_get(name))
                for name in aliases
                if self._env_get(name)
            ]
        key = self._get_api_key(provider)
        return [(provider.get("api_key_env", ""), key)] if key else []

    def _build_prof_client(
        self,
        provider: dict,
        *,
        call_site_id: str,
        timeout: float,
        context: LLMCallContext | None = None,
    ) -> Any:
        """Build ProfessionalizeClient from provider config for metrics-aware transport.

        base_url_env (if present in registry) takes precedence over base_url,
        allowing GPT_OSS_ENDPOINT to override the hardcoded base URL.
        """
        chat_cfg = provider.get("chat", {})
        embed_cfg = provider.get("embeddings", {})
        raw_key = self._get_api_key(provider)
        base_url = self._resolve_base_url(provider)
        return ProfessionalizeClient(
            base_url=base_url,
            api_key=raw_key if raw_key else None,
            default_chat_model=chat_cfg.get("model"),
            default_embedding_model=embed_cfg.get("model"),
            timeout=timeout,
            http_client=self._http_client,
            call_site_id=call_site_id,
            credential_candidates=self._get_api_key_candidates(provider),
            config_digest=self._config_digest,
            consumer_id=context.consumer_id if context else None,
            parent_run_id=context.run_id if context else None,
            job_type=context.job_type if context else None,
            work_slice_id=context.work_slice_id if context else None,
            retry_max_attempts=(provider.get("retry") or {}).get("max_attempts", 1),
            retry_statuses=(provider.get("retry") or {}).get("retry_statuses", []),
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
        log.warning(
            "Fell back from %s (%s) to %s",
            first_failure.provider, first_failure.status.value, fallback_provider,
        )
        return ""

    # -- Registry access ----------------------------------------------------

    def get_provider_config(self, name: str) -> dict | None:
        """Return raw provider config dict by name."""
        error = self._reload_registry()
        if error:
            raise RuntimeError(error)
        return self._registry["providers"].get(name)

    def get_embed_dimensions(self, provider_name: str) -> int | None:
        """Return expected embedding dimensions for a provider."""
        cfg = self.get_provider_config(provider_name)
        if cfg and cfg.get("embeddings"):
            return cfg["embeddings"].get("embed_dimensions")
        return None

    def is_operation_available(self, operation: str) -> bool:
        """Return whether any configured provider for an operation is usable."""
        error = self._reload_registry()
        if error:
            return False
        allowed = set(
            self._registry.get("operation_profiles", {})
            .get(operation, {})
            .get("providers", [])
        )
        for name, provider in self._providers:
            if allowed and name not in allowed:
                continue
            if self._get_api_key(provider) is not None:
                return True
        return False


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
