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
        # Should return False (no server running, or requests missing)
        assert client.is_available() is False


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
