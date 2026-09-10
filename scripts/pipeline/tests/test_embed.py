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
