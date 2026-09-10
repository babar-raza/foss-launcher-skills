"""Tests for scripts/pipeline/embed.py — TF-IDF and utility functions."""

# sys.path is set by tests/conftest.py — no manual insert needed here.
import embed


class TestTokenize:
    def test_basic(self):
        tokens = embed.tokenize("The quick brown fox jumps over the lazy dog")
        assert "quick" in tokens
        assert "brown" in tokens
        # stopwords removed
        assert "the" not in tokens
        assert "over" not in tokens

    def test_empty(self):
        assert embed.tokenize("") == []
        assert embed.tokenize("   ") == []

    def test_short_words_removed(self):
        tokens = embed.tokenize("I am an ok so do it go")
        # all words <= 2 chars should be removed
        assert all(len(t) > 2 for t in tokens)

    def test_case_insensitive(self):
        tokens = embed.tokenize("Python PYTHON python")
        assert all(t == "python" for t in tokens)


class TestComputeTf:
    def test_basic(self):
        tf = embed.compute_tf(["hello", "world", "hello"])
        assert abs(tf["hello"] - 2 / 3) < 1e-9
        assert abs(tf["world"] - 1 / 3) < 1e-9

    def test_empty(self):
        assert embed.compute_tf([]) == {}


class TestComputeIdf:
    def test_basic(self):
        docs = [["hello", "world"], ["hello", "python"]]
        idf = embed.compute_idf(docs)
        # "hello" in both docs: log(1 + 2/2) = log(2)
        import math
        assert abs(idf["hello"] - math.log(2)) < 1e-9
        # "world" in 1 doc: log(1 + 2/1) = log(3)
        assert abs(idf["world"] - math.log(3)) < 1e-9

    def test_empty(self):
        assert embed.compute_idf([]) == {}


class TestCosineSimilarity:
    def test_identical(self):
        vec = {"a": 1.0, "b": 2.0}
        assert abs(embed.cosine_similarity(vec, vec) - 1.0) < 1e-9

    def test_orthogonal(self):
        vec1 = {"a": 1.0}
        vec2 = {"b": 1.0}
        assert embed.cosine_similarity(vec1, vec2) == 0.0

    def test_empty(self):
        assert embed.cosine_similarity({}, {"a": 1.0}) == 0.0
        assert embed.cosine_similarity({}, {}) == 0.0

    def test_partial_overlap(self):
        vec1 = {"a": 1.0, "b": 1.0}
        vec2 = {"a": 1.0, "c": 1.0}
        sim = embed.cosine_similarity(vec1, vec2)
        assert 0.0 < sim < 1.0


class TestTfidfVector:
    def test_basic(self):
        import math
        tokens = ["hello", "world"]
        idf = {"hello": math.log(2), "world": math.log(3)}
        vec = embed.compute_tfidf_vector(tokens, idf)
        assert abs(vec["hello"] - 0.5 * math.log(2)) < 1e-9
        assert abs(vec["world"] - 0.5 * math.log(3)) < 1e-9


class TestEmbeddingClientWithoutRequests:
    def test_unavailable_without_requests(self):
        client = embed.EmbeddingClient("http://localhost:9999", "test-model")
        client._router.is_operation_available = MagicMock(return_value=False)
        assert client.is_available() is False

    def test_embed_batch_preserves_run_context(self):
        from commands.ops.llm_router import (
            CallResult,
            EmbeddingProfile,
            EndpointStatus,
            LLMCallContext,
        )

        context = LLMCallContext(
            consumer_id="embed-api-index",
            run_id="run-context-test",
            job_type="knowledge-embedding",
            work_slice_id="cells/net/api",
        )
        client = embed.EmbeddingClient(
            "ignored",
            "ignored",
            context=context,
        )
        client._router.call_embeddings = MagicMock(
            return_value=CallResult(
                provider="professionalize",
                model="qwen3-embedding-8b",
                status=EndpointStatus.OK,
                data=[[0.1] * 512],
                embedding_profile=EmbeddingProfile(
                    "profile", "professionalize", "qwen3-embedding-8b", 512, "digest"
                ),
            )
        )

        client.embed_batch(["one"])

        assert client._router.call_embeddings.call_args.kwargs["context"] == context


# ---------------------------------------------------------------------------
# embed_and_save — dimension validation and metadata (TC-11)
# ---------------------------------------------------------------------------

import json
import pytest
from pathlib import Path
from unittest.mock import patch, MagicMock


class TestEmbedAndSaveDimensionValidation:
    """Test that embed_and_save validates dimensions and writes metadata."""

    def _mock_client(self, model="test-model", vectors=None):
        client = MagicMock(spec=embed.EmbeddingClient)
        client.model = model
        client.embed_batch.return_value = vectors or []
        return client

    def test_correct_dims_writes_successfully(self, tmp_path):
        vectors = [[0.1] * 128, [0.2] * 128]
        client = self._mock_client(vectors=vectors)
        out = tmp_path / "test.vectors.json"

        embed.embed_and_save(
            client, {"a": "text a", "b": "text b"}, out,
            expected_dimensions=128, provider="test-provider",
        )

        data = json.loads(out.read_text())
        assert data["dimensions"] == 128
        assert data["provider"] == "test-provider"
        assert data["count"] == 2
        assert len(data["vectors"]["a"]) == 128

    def test_wrong_dims_raises_valueerror(self, tmp_path):
        vectors = [[0.1] * 512, [0.2] * 512]
        client = self._mock_client(vectors=vectors)
        out = tmp_path / "test.vectors.json"

        with pytest.raises(ValueError, match="Dimension mismatch"):
            embed.embed_and_save(
                client, {"a": "text a", "b": "text b"}, out,
                expected_dimensions=128,
            )

        # File must NOT exist — refused to write
        assert not out.exists()

    def test_no_expected_dims_skips_validation(self, tmp_path):
        vectors = [[0.1] * 999]
        client = self._mock_client(vectors=vectors)
        out = tmp_path / "test.vectors.json"

        embed.embed_and_save(client, {"a": "text a"}, out)

        data = json.loads(out.read_text())
        assert data["dimensions"] == 999
        assert data["provider"] == ""

    def test_metadata_fields_present(self, tmp_path):
        vectors = [[0.5] * 4096]
        client = self._mock_client(model="qwen3-embedding-8b", vectors=vectors)
        out = tmp_path / "test.vectors.json"

        embed.embed_and_save(
            client, {"cls1": "class Foo"}, out,
            expected_dimensions=4096, provider="professionalize",
        )

        data = json.loads(out.read_text())
        assert "dimensions" in data
        assert "provider" in data
        assert data["model"] == "qwen3-embedding-8b"
        assert data["dimensions"] == 4096
        assert data["provider"] == "professionalize"


class TestPickClientReturnsTier:
    """Test that _pick_client returns (client, tier) tuple."""

    def test_returns_none_tuple_when_no_client(self):
        config = {"tiers": []}
        client, tier = embed._pick_client(config)
        assert client is None
        assert tier is None

    def test_real_default_config_does_not_raise_keyerror(self, monkeypatch):
        """Regression guard (RC1, TC-VEC-01-B): DEFAULT_CONFIG's tier dicts
        (id/provider/model/dimensions/last_embedded) never define an
        "endpoint" key, but _pick_client did a raw tier["endpoint"] subscript
        (embed.py:471) — an unconditional KeyError on any fresh checkout,
        since no knowledge/_vectors/config.json exists to patch it in. The
        prior test above uses a synthetic {"tiers": []}, which sidesteps the
        defect entirely (the loop body never runs). This test exercises the
        real production DEFAULT_CONFIG so the defect cannot hide again."""
        for var in ("LLM_API_KEY", "GPT_OSS_API_KEY", "LITELLM_KEY", "PROFESSIONALIZE_API_KEY"):
            monkeypatch.delenv(var, raising=False)
        client, tier = embed._pick_client(embed.DEFAULT_CONFIG)
        # No credentials configured -> no tier reports available. The point of
        # this test is that reaching this assertion at all (no KeyError raised
        # by the tier-dict subscript) proves the defect is fixed.
        assert client is None
        assert tier is None


class TestEmbedKnowledgeTierDispatch:
    """Regression guard (RC1, TC-VEC-01-B): embed_knowledge()'s standard-mode
    tier loop must not crash with the same tier["endpoint"] KeyError."""

    def test_real_default_config_tier_loop_does_not_raise_keyerror(self, tmp_path, monkeypatch):
        for var in ("LLM_API_KEY", "GPT_OSS_API_KEY", "LITELLM_KEY", "PROFESSIONALIZE_API_KEY"):
            monkeypatch.delenv(var, raising=False)
        merged = tmp_path / "widgets" / "python" / "merged"
        merged.mkdir(parents=True)
        (merged / "claims.json").write_text(
            json.dumps([{"claim_id": "CLM-1", "kind": "feature", "text": "does a thing"}]),
            encoding="utf-8",
        )
        # config_path points at a file that does not exist, so
        # load_or_create_config() falls back to a deep copy of the real
        # DEFAULT_CONFIG — deterministic regardless of ambient repo state.
        config_path = tmp_path / "config.json"
        # Must not raise KeyError. With no credentials configured, both tiers
        # report unavailable and the function returns having embedded
        # nothing — reaching that point at all is the proof the defect is
        # fixed at this call site too.
        embed.embed_knowledge(
            "widgets", "python", config_path=config_path, knowledge_root=tmp_path
        )


# ---------------------------------------------------------------------------
# chunk_content_pages — all 5 site roots covered (RC-2 regression guard)
# ---------------------------------------------------------------------------

import content_discovery  # noqa: E402  (sys.path added by conftest.py)


class TestChunkContentPagesAllSites:
    """Regression guard: chunk_content_pages must cover all 5 content sites."""

    SITE_NAMES = [
        "docs.aspose.org",
        "kb.aspose.org",
        "blog.aspose.org",
        "reference.aspose.org",
        "products.aspose.org",
    ]

    def _make_site_files(self, tmp_path: Path, family: str, platform: str) -> dict[str, Path]:
        """Create one .md file per site under tmp_path."""
        site_files: dict[str, Path] = {}
        for site_name, pattern in content_discovery.SITE_PATHS:
            site_dir = Path(pattern.format(family=family, platform=platform))
            # Reroute under tmp_path to avoid writing to actual content/
            relative = site_dir.relative_to(site_dir.anchor) if site_dir.is_absolute() else site_dir
            local_dir = tmp_path / relative
            local_dir.mkdir(parents=True, exist_ok=True)
            md = local_dir / "sample.md"
            md.write_text(
                f"# Sample for {site_name}\n\nThis is a paragraph long enough to be chunked.\n",
                encoding="utf-8",
            )
            site_files[site_name] = md
        return site_files

    def test_all_five_sites_covered(self, tmp_path, monkeypatch):
        """Every site in SITE_PATHS must contribute chunks when its dir exists."""
        family, platform = "testfam", "testplat"

        # Build fake SITE_PATHS pointing entirely inside tmp_path
        fake_site_paths = []
        for site_name, _ in content_discovery.SITE_PATHS:
            local_dir = tmp_path / "content" / site_name.replace(".", "_") / "{family}" / "{platform}"
            fake_site_paths.append((site_name, str(local_dir)))

        # Create one file per site
        for site_name, pattern in fake_site_paths:
            site_dir = Path(pattern.format(family=family, platform=platform))
            site_dir.mkdir(parents=True, exist_ok=True)
            (site_dir / "page.md").write_text(
                "# Test\n\nA paragraph with enough text to be included as a chunk.\n",
                encoding="utf-8",
            )

        monkeypatch.setattr(content_discovery, "SITE_PATHS", fake_site_paths)

        chunks = embed.chunk_content_pages(family, platform)
        assert len(chunks) >= len(fake_site_paths), (
            f"Expected chunks from all {len(fake_site_paths)} sites; got {len(chunks)} chunks. "
            "chunk_content_pages may still be using hardcoded site paths."
        )

        # Every site dir should appear in at least one chunk key
        covered_sites = set()
        for key in chunks:
            for site_name, pattern in fake_site_paths:
                site_dir = str(Path(pattern.format(family=family, platform=platform)))
                if site_dir in key:
                    covered_sites.add(site_name)

        missing = set(name for name, _ in fake_site_paths) - covered_sites
        assert not missing, (
            f"The following sites produced no chunks: {missing}. "
            "chunk_content_pages is not using SITE_PATHS for all sites."
        )


# ---------------------------------------------------------------------------
# embed_api_index — content-addressed profile IDs + advisory lock (RC5, TC-VEC-02)
#
# embed_api_index()'s canonical/official path (the ONLY path that has ever
# produced working output in this repo's history) only executes when BOTH
# config_path AND knowledge_root are None (embed.py's own "official path"
# gate) — passing a custom knowledge_root for test isolation silently falls
# through to the unrelated legacy tier-dispatch branch instead. embed_api_index
# had ZERO existing tests before this class (confirmed: no prior references in
# this file). These tests use monkeypatch.chdir(tmp_path) + a patched
# LLMRouter instead of the knowledge_root parameter, so the REAL official path
# runs against an isolated filesystem root rather than the live repo.
# ---------------------------------------------------------------------------

import os
import threading
import time


class _FakeEmbeddingProfile:
    def __init__(
        self,
        provider="professionalize",
        model="qwen3-embedding-8b",
        dimensions=512,
        config_digest="abc123def456",
    ):
        self.provider = provider
        self.model = model
        self.dimensions = dimensions
        self.config_digest = config_digest


class _FakeCallResult:
    def __init__(self, data, profile):
        from commands.ops.llm_router import EndpointStatus

        self.status = EndpointStatus.OK
        self.data = data
        self.embedding_profile = profile
        self.metrics_events = []
        self.error = ""


class _FakeRouter:
    """Stand-in for LLMRouter — no network calls, deterministic vectors."""

    def __init__(self, *a, **kw):
        pass

    def call_embeddings(self, texts, context, operation):
        vectors = [[0.1] * 512 for _ in texts]
        return _FakeCallResult(vectors, _FakeEmbeddingProfile())


def _write_api_surface(root: Path, family: str, platform: str, class_names: list) -> Path:
    merged = root / "knowledge" / family / platform / "merged"
    merged.mkdir(parents=True, exist_ok=True)
    api_path = merged / "api_surface.json"
    api_path.write_text(
        json.dumps(
            [
                {"name": n, "method_details": [], "property_details": [], "docstring": ""}
                for n in class_names
            ]
        ),
        encoding="utf-8",
    )
    return api_path


def _read_active_profile_id(tmp_path: Path, family: str, platform: str) -> str:
    active = tmp_path / "knowledge" / "_vectors" / family / platform / "active.json"
    return json.loads(active.read_text(encoding="utf-8"))["profile_id"]


@pytest.fixture(autouse=True)
def _fake_llm_router_seam():
    """Testing seam (AGENTS.md §16): DI via embed.configure(), not a monkeypatch
    on commands.ops.llm_router.LLMRouter directly (a T2 internal-patch violation)."""
    embed.configure(llm_router_cls=_FakeRouter)
    yield
    embed.configure()


class TestEmbedApiIndexProfileAddressing:
    """TC-VEC-02-A: profile_id must be content-addressed, not just config-addressed."""

    def test_same_source_same_config_same_profile_id(self, tmp_path, monkeypatch):
        monkeypatch.chdir(tmp_path)
        _write_api_surface(tmp_path, "widgets", "python", ["Foo", "Bar"])

        assert embed.embed_api_index("widgets", "python") is not None
        profile_id_1 = _read_active_profile_id(tmp_path, "widgets", "python")

        assert embed.embed_api_index("widgets", "python") is not None
        profile_id_2 = _read_active_profile_id(tmp_path, "widgets", "python")

        assert profile_id_1 == profile_id_2

    def test_changed_source_produces_new_profile_without_destroying_old(self, tmp_path, monkeypatch):
        monkeypatch.chdir(tmp_path)
        _write_api_surface(tmp_path, "widgets", "python", ["Foo", "Bar"])

        assert embed.embed_api_index("widgets", "python") is not None
        profile_id_1 = _read_active_profile_id(tmp_path, "widgets", "python")

        # Mutate source content — must NOT collide with the prior profile_id.
        _write_api_surface(tmp_path, "widgets", "python", ["Foo", "Bar", "Baz"])
        assert embed.embed_api_index("widgets", "python") is not None
        profile_id_2 = _read_active_profile_id(tmp_path, "widgets", "python")

        assert profile_id_1 != profile_id_2, (
            "profile_id did not change when source content changed — RC5 not fixed "
            "(profile storage is still config-addressed only, not content-addressed)."
        )

        # The prior generation must remain on disk (non-destructive supersession —
        # this is what makes 'profile-versioned' actually true).
        old_dir = tmp_path / "knowledge" / "_vectors" / "widgets" / "python" / "profiles" / profile_id_1
        assert old_dir.exists(), "changed-content rerun destroyed the prior profile directory"
        assert (old_dir / "manifest.json").exists()
        assert (old_dir / "api.vectors.json").exists()

    def test_profile_id_includes_source_hash_prefix(self, tmp_path, monkeypatch):
        """Pins the exact format so a future refactor can't silently drop the fix."""
        import hashlib

        monkeypatch.chdir(tmp_path)
        api_path = _write_api_surface(tmp_path, "widgets", "python", ["Foo"])

        embed.embed_api_index("widgets", "python")
        profile_id = _read_active_profile_id(tmp_path, "widgets", "python")

        source_hash = hashlib.sha256(api_path.read_bytes()).hexdigest()
        assert profile_id.endswith(source_hash[:8]), (
            f"profile_id {profile_id!r} does not end with the source content hash "
            f"prefix {source_hash[:8]!r}"
        )


class TestEmbedApiIndexWriteLock:
    """TC-VEC-02-B: advisory write-phase lock — happy path and stale-bypass."""

    def test_happy_path_lock_created_and_released(self, tmp_path, monkeypatch):
        monkeypatch.chdir(tmp_path)
        _write_api_surface(tmp_path, "widgets", "python", ["Foo"])

        assert embed.embed_api_index("widgets", "python") is not None

        lock_path = tmp_path / "knowledge" / "_vectors" / "widgets" / "python" / "write.lock"
        assert not lock_path.exists(), "write lock was not released after a successful run"

    def test_stale_lock_does_not_block_a_new_run(self, tmp_path, monkeypatch):
        """A lock left behind by a crashed/dead holder must be bypassed, not block forever."""
        monkeypatch.chdir(tmp_path)
        _write_api_surface(tmp_path, "widgets", "python", ["Foo"])

        lock_dir = tmp_path / "knowledge" / "_vectors" / "widgets" / "python"
        lock_dir.mkdir(parents=True, exist_ok=True)
        lock_path = lock_dir / "write.lock"
        # Simulate a lock left by a definitely-dead pid (0 is never a real process
        # here), written far enough in the past to be past FileLock's default
        # stale_seconds (120s) if pid-liveness alone didn't already resolve it.
        lock_path.write_text("999999999:0", encoding="utf-8")
        old_time = time.time() - 3600
        os.utime(lock_path, (old_time, old_time))

        result = embed.embed_api_index("widgets", "python")
        assert result is not None, "a stale lock from a dead/expired holder blocked the run"
        assert not lock_path.exists(), "stale lock was not cleaned up after being stolen"


class TestEmbedApiIndexConcurrency:
    """TC-VEC-02-C: two overlapping writers for the same product must never corrupt
    each other's output — the test that directly targets RC5."""

    def test_interleaved_writers_different_source_never_corrupt_active_profile(
        self, tmp_path, monkeypatch
    ):
        monkeypatch.chdir(tmp_path)

        _write_api_surface(tmp_path, "widgets", "python", ["Foo", "Bar"])

        # embed_api_index reads api_surface.json twice: once as text (to build the
        # class-entry texts — irrelevant to this test, the FakeRouter ignores
        # content) and once as bytes, right before computing profile_id, to derive
        # source_hash. Patching only read_bytes — and forcing both threads to
        # rendezvous inside it via a barrier — makes two concurrent calls resolve
        # to two DIFFERENT source snapshots ("snapshot-a" vs "snapshot-b") with
        # their write phases genuinely overlapping, without racing a single shared
        # file on disk (which would let whichever write lands last silently decide
        # both threads' content — not the scenario RC5 is about).
        results = {}
        barrier = threading.Barrier(2)
        fake_contents = {"a": b"fake-source-snapshot-a", "b": b"fake-source-snapshot-b"}
        real_read_bytes = Path.read_bytes

        def fake_read_bytes(self_path):
            name = threading.current_thread().name
            if self_path.name == "api_surface.json" and name in fake_contents:
                barrier.wait(timeout=5)
                return fake_contents[name]
            return real_read_bytes(self_path)

        monkeypatch.setattr(Path, "read_bytes", fake_read_bytes)

        def _run(key):
            results[key] = embed.embed_api_index("widgets", "python")

        t1 = threading.Thread(target=_run, args=("a",), name="a")
        t2 = threading.Thread(target=_run, args=("b",), name="b")
        t1.start()
        t2.start()
        t1.join(timeout=10)
        t2.join(timeout=10)

        assert results.get("a") is not None
        assert results.get("b") is not None

        # Whichever run's write finished last, active.json must point at a
        # self-consistent profile: its manifest's declared count/source_hash must
        # match the vectors file actually present at that exact path.
        root = tmp_path / "knowledge" / "_vectors" / "widgets" / "python"
        active_profile_id = json.loads((root / "active.json").read_text(encoding="utf-8"))["profile_id"]
        profile_dir = root / "profiles" / active_profile_id
        manifest = json.loads((profile_dir / "manifest.json").read_text(encoding="utf-8"))
        vectors_payload = json.loads((profile_dir / "api.vectors.json").read_text(encoding="utf-8"))

        assert manifest["count"] == len(vectors_payload["vectors"]), (
            "active profile's manifest count does not match its own vectors file — "
            "a chimeric half-old-half-new profile was produced (RC5 not fixed)"
        )
        assert manifest["profile_id"] == vectors_payload["profile_id"] == active_profile_id

        # Both writers' profile directories must exist independently — no shared
        # file writes / in-place overwrite between two different source contents.
        existing_profile_dirs = list((root / "profiles").iterdir())
        assert len(existing_profile_dirs) == 2, (
            f"expected 2 distinct profile directories (one per distinct source "
            f"content), found {len(existing_profile_dirs)}: {existing_profile_dirs}"
        )
