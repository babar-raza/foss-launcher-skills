"""HARDEN-A6: rerun-consistency harness for the S-37 enrich LLM call site.

Proves the A4 contract at the unit level:
  - cache enabled + identical input  -> ZERO new LLM calls, byte-identical output
  - cache bypassed (forced fresh)    -> real calls happen, fresh output still
                                        refreshes the cache for future runs
  - changed identity (api sha)       -> cache miss (no false sharing)
Only the LLM transport is faked; cache key construction, load/save, and the
model-drift marker run for real.
"""
from __future__ import annotations

import sys
from pathlib import Path

import pytest

_PIPELINE_DIR = Path(__file__).resolve().parent.parent
if str(_PIPELINE_DIR) not in sys.path:
    sys.path.insert(0, str(_PIPELINE_DIR))
_LIB_DIR = _PIPELINE_DIR / "lib"
if str(_LIB_DIR) not in sys.path:
    sys.path.insert(0, str(_LIB_DIR))

from commands.knowledge import enrich as enrich_mod  # noqa: E402
from llm_output_cache import LLMOutputCache, build_cache_key, sha256_text  # noqa: E402


class _FakeResult:
    def __init__(self, data, provider="fake", model="fake-model-1"):
        from lib.llm_router import EndpointStatus
        self.status = EndpointStatus.OK
        self.data = data
        self.provider = provider
        self.model = model
        self.metrics_events = []


class _FakeRouter:
    """Call-counting fake transport; returns different data on each call."""

    def __init__(self, static_data=None):
        self.calls = 0
        self.static_data = static_data

    def call_chat(self, *args, **kwargs):
        self.calls += 1
        data = self.static_data if self.static_data is not None else [
            {"claim": f"fresh output number {self.calls}"}
        ]
        return _FakeResult(data)


@pytest.fixture(autouse=True)
def _reset_router_singleton():
    original = enrich_mod._router
    yield
    enrich_mod._router = original


def test_cache_hit_zero_calls_byte_identical(tmp_path):
    fake = _FakeRouter(static_data=[{"claim": "alpha"}])
    enrich_mod._router = fake
    cache = LLMOutputCache("tfam", "tplat", "enrich", reports_root=tmp_path)
    extra = ["tfam", "tplat", "apisha-1"]

    out1, model1 = enrich_mod._llm_call("SYS", "USER", cache=cache, cache_extra=extra)
    assert fake.calls == 1
    assert out1 == [{"claim": "alpha"}]
    assert model1 == "fake/fake-model-1"

    out2, model2 = enrich_mod._llm_call("SYS", "USER", cache=cache, cache_extra=extra)
    assert fake.calls == 1, "second identical-input call must be served from cache"
    assert out2 == out1
    assert model2 == "fake/fake-model-1"


def test_changed_identity_or_prompt_misses(tmp_path):
    fake = _FakeRouter()
    enrich_mod._router = fake
    cache = LLMOutputCache("tfam", "tplat", "enrich", reports_root=tmp_path)

    enrich_mod._llm_call("SYS", "USER", cache=cache, cache_extra=["tfam", "tplat", "sha-A"])
    assert fake.calls == 1
    # different api-surface sha -> different key -> real call
    enrich_mod._llm_call("SYS", "USER", cache=cache, cache_extra=["tfam", "tplat", "sha-B"])
    assert fake.calls == 2
    # different prompt -> different key -> real call
    enrich_mod._llm_call("SYS", "USER v2", cache=cache, cache_extra=["tfam", "tplat", "sha-A"])
    assert fake.calls == 3


def test_forced_fresh_bypasses_reads_but_still_stores(tmp_path):
    fake = _FakeRouter()
    enrich_mod._router = fake
    extra = ["tfam", "tplat", "apisha-1"]

    warm = LLMOutputCache("tfam", "tplat", "enrich", reports_root=tmp_path)
    out1, _ = enrich_mod._llm_call("SYS", "USER", cache=warm, cache_extra=extra)
    assert fake.calls == 1

    bypass = LLMOutputCache("tfam", "tplat", "enrich", reports_root=tmp_path, enabled=False)
    out2, _ = enrich_mod._llm_call("SYS", "USER", cache=bypass, cache_extra=extra)
    assert fake.calls == 2, "bypassed cache must force a real call"
    assert out2 != out1, "fake returns call-numbered output — proves a real fresh call"

    # The forced-fresh output refreshed the stored entry for future cached runs
    read_back = LLMOutputCache("tfam", "tplat", "enrich", reports_root=tmp_path)
    out3, _ = enrich_mod._llm_call("SYS", "USER", cache=read_back, cache_extra=extra)
    assert fake.calls == 2, "cache hit again after forced refresh"
    assert out3 == out2


def test_llm_failure_never_cached(tmp_path):
    class _FailRouter:
        def __init__(self):
            self.calls = 0

        def call_chat(self, *a, **k):
            self.calls += 1
            from lib.llm_router import EndpointStatus

            class _R:
                status = EndpointStatus.DOWN if hasattr(EndpointStatus, "DOWN") else None
                data = None
                metrics_events = []
            r = _R()
            # Whatever non-OK status exists — emulate failure by not being OK
            return r

    fake = _FailRouter()
    enrich_mod._router = fake
    cache = LLMOutputCache("tfam", "tplat", "enrich", reports_root=tmp_path)
    extra = ["tfam", "tplat", "apisha-1"]

    out, model = enrich_mod._llm_call("SYS", "USER", cache=cache, cache_extra=extra)
    assert out is None and model == ""
    # failure was not cached: a new call goes to the transport again
    enrich_mod._llm_call("SYS", "USER", cache=cache, cache_extra=extra)
    assert fake.calls == 2


def test_model_drift_detected_logged(tmp_path, caplog):
    import logging
    cache = LLMOutputCache("tfam", "tplat", "enrich", reports_root=tmp_path)
    key1 = build_cache_key(["a", sha256_text("s"), sha256_text("u")])
    key2 = build_cache_key(["b", sha256_text("s"), sha256_text("u")])
    with caplog.at_level(logging.WARNING, logger="llm_output_cache"):
        cache.save(key1, {"x": 1}, "prov/model-v1")
        cache.save(key2, {"x": 2}, "prov/model-v2")
    assert any("MODEL_DRIFT_DETECTED" in rec.message for rec in caplog.records)


def test_semantic_error_payload_never_cached(tmp_path):
    """R2: an HTTP-200 completion carrying an error body (TC-2's real case,
    e.g. {"error": "rate_limited"}) must NOT be cached — otherwise every rerun
    replays the failure with zero LLM calls until the input changes."""
    fake = _FakeRouter(static_data={"error": "rate_limited"})
    enrich_mod._router = fake
    cache = LLMOutputCache("tfam", "tplat", "enrich", reports_root=tmp_path)
    extra = ["tfam", "tplat", "apisha-1"]

    out1, _ = enrich_mod._llm_call("SYS", "USER", cache=cache, cache_extra=extra)
    assert out1 == {"error": "rate_limited"}  # still returned (TC-2 handles it)
    assert fake.calls == 1
    # NOT cached: the identical rerun goes to the transport again
    enrich_mod._llm_call("SYS", "USER", cache=cache, cache_extra=extra)
    assert fake.calls == 2

    # Whereas a claims-bearing dict IS cacheable
    fake2 = _FakeRouter(static_data={"claims": [{"claim": "x"}]})
    enrich_mod._router = fake2
    enrich_mod._llm_call("SYS2", "USER2", cache=cache, cache_extra=extra)
    enrich_mod._llm_call("SYS2", "USER2", cache=cache, cache_extra=extra)
    assert fake2.calls == 1


def test_cache_write_failure_is_nonfatal(tmp_path):
    """R3: a failed cache WRITE (unserializable output, locked file, disk full)
    must never outrank a successful generation — save() swallows and logs."""
    cache = LLMOutputCache("tfam", "tplat", "enrich", reports_root=tmp_path)
    key = build_cache_key(["k", sha256_text("s"), sha256_text("u")])
    cache.save(key, object(), "prov/model-v1")  # unserializable — must not raise
    assert cache.load(key) is None  # nothing stored


def test_enrich_smoke_no_conftest_path_masking(tmp_path):
    """R1: enrich() must import its cache dependency in a BARE interpreter with
    only the CLI's own sys.path setup — the lib-import crash was invisible to
    all 226 in-process tests because pytest's conftest put lib/ on the path.
    (The CLI main() additionally has a repo-level prereq gate that rejects
    unknown products before reaching enrich(), so this drives enrich() itself.)
    """
    import subprocess
    scout = tmp_path / "know" / "tfam" / "tplat" / "scout"
    scout.mkdir(parents=True)
    (scout / "api_surface.json").write_text("[]", encoding="utf-8")
    (scout / "claims.json").write_text("[]", encoding="utf-8")

    repo_root = _PIPELINE_DIR.parent.parent
    code = (
        "import sys\n"
        f"sys.path.insert(0, {str(_PIPELINE_DIR)!r})\n"
        "from commands.knowledge import enrich as e\n"
        f"ok = e.enrich('tfam', 'tplat', {str(tmp_path / 'know')!r}, no_llm=True)\n"
        "sys.exit(0 if ok else 1)\n"
    )
    result = subprocess.run(
        [sys.executable, "-c", code],
        capture_output=True, text=True, timeout=120, cwd=str(repo_root),
    )
    assert "ModuleNotFoundError" not in result.stderr, result.stderr[-800:]
    assert result.returncode == 0, (result.stdout[-400:], result.stderr[-800:])
