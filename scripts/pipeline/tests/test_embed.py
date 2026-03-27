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
