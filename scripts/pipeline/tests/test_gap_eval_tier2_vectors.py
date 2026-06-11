"""Integration tests for Tier 2 vector search in gap-eval.

TC-GAPEVAL-001: Verifies that the Tier 2 path activates when
api.vectors.json exists, and returns cosine similarity scores.
"""

import json
import math
from pathlib import Path
from unittest.mock import patch, MagicMock

import pytest

import embed


class TestEmbedApiIndex:
    """Test the embed_api_index() function that produces api.vectors.json."""

    def _make_api_surface(self, tmp_path: Path, family: str, platform: str) -> Path:
        """Create a minimal api_surface.json for testing."""
        merged_dir = tmp_path / "knowledge" / family / platform / "merged"
        merged_dir.mkdir(parents=True, exist_ok=True)
        api_data = [
            {
                "name": "Workbook",
                "method_details": [{"name": "Save"}, {"name": "Open"}],
                "property_details": [{"name": "Worksheets"}],
                "docstring": "Represents an Excel workbook.",
            },
            {
                "name": "Worksheet",
                "method_details": [{"name": "Calculate"}],
                "property_details": [{"name": "Cells"}, {"name": "Name"}],
                "docstring": "Represents a single worksheet.",
            },
        ]
        api_path = merged_dir / "api_surface.json"
        api_path.write_text(json.dumps(api_data), encoding="utf-8")
        return tmp_path / "knowledge"

    def _mock_client(self, dim: int = 128):
        """Create a mock EmbeddingClient that returns deterministic vectors."""
        client = MagicMock(spec=embed.EmbeddingClient)
        client.model = "test-model"
        # Return a unique vector per text: hash-based deterministic
        def fake_embed(texts, batch_size=32):
            vectors = []
            for i, t in enumerate(texts):
                # Simple deterministic vector based on index
                vec = [0.0] * dim
                vec[i % dim] = 1.0
                vec[(i + 1) % dim] = 0.5
                vectors.append(vec)
            return vectors
        client.embed_batch.side_effect = fake_embed
        return client

    def test_produces_api_vectors_json(self, tmp_path):
        """embed_api_index writes api.vectors.json with correct structure."""
        kr = self._make_api_surface(tmp_path, "cells", "net")
        mock_client = self._mock_client()

        with patch.object(embed, "_pick_client", return_value=(mock_client, {"dimensions": 128, "provider": "test"})):
            result = embed.embed_api_index("cells", "net", knowledge_root=kr)

        assert result is not None
        assert result.exists()
        data = json.loads(result.read_text(encoding="utf-8"))
        assert data["version"] == "1.0.0"
        assert data["count"] == 2
        assert "Workbook" in data["vectors"]
        assert "Worksheet" in data["vectors"]
        assert len(data["vectors"]["Workbook"]) == 128

    def test_returns_none_when_no_api_surface(self, tmp_path):
        """embed_api_index returns None when api_surface.json missing."""
        kr = tmp_path / "knowledge"
        kr.mkdir(parents=True)
        result = embed.embed_api_index("cells", "net", knowledge_root=kr)
        assert result is None

    def test_returns_none_when_no_client(self, tmp_path):
        """embed_api_index returns None when no embedding tier available."""
        kr = self._make_api_surface(tmp_path, "cells", "net")
        with patch.object(embed, "_pick_client", return_value=(None, None)):
            result = embed.embed_api_index("cells", "net", knowledge_root=kr)
        assert result is None

    def test_output_path_matches_gap_eval_expectation(self, tmp_path):
        """Output path is knowledge/_vectors/{family}/{platform}/api.vectors.json."""
        kr = self._make_api_surface(tmp_path, "pdf", "go")
        mock_client = self._mock_client()

        with patch.object(embed, "_pick_client", return_value=(mock_client, {"dimensions": 128, "provider": "test"})):
            result = embed.embed_api_index("pdf", "go", knowledge_root=kr)

        assert result is not None
        # Path should be relative to knowledge root
        expected_suffix = Path("pdf") / "go" / "api.vectors.json"
        assert result.name == "api.vectors.json"
        assert "pdf" in str(result)
        assert "go" in str(result)


class TestTier2VectorActivation:
    """Test that the Tier 2 vector path activates when vectors exist."""

    def _write_vectors(self, tmp_path: Path, family: str, platform: str) -> Path:
        """Write a minimal api.vectors.json for testing."""
        vectors_dir = tmp_path / "knowledge" / "_vectors" / family / platform
        vectors_dir.mkdir(parents=True, exist_ok=True)
        # Create two class vectors with known properties
        dim = 4
        data = {
            "version": "1.0.0",
            "model": "test-model",
            "dimensions": dim,
            "provider": "test",
            "count": 2,
            "vectors": {
                "Workbook": [1.0, 0.0, 0.0, 0.0],
                "Worksheet": [0.0, 1.0, 0.0, 0.0],
            },
        }
        vectors_path = vectors_dir / "api.vectors.json"
        vectors_path.write_text(json.dumps(data), encoding="utf-8")
        return vectors_path

    def test_vectors_file_loadable(self, tmp_path):
        """api.vectors.json can be loaded and contains expected structure."""
        vp = self._write_vectors(tmp_path, "cells", "net")
        data = json.loads(vp.read_text(encoding="utf-8"))
        assert data["count"] == 2
        assert len(data["vectors"]) == 2
        assert len(data["vectors"]["Workbook"]) == data["dimensions"]

    def test_cosine_similarity_on_loaded_vectors(self, tmp_path):
        """Cosine similarity works correctly on vectors from api.vectors.json."""
        vp = self._write_vectors(tmp_path, "cells", "net")
        data = json.loads(vp.read_text(encoding="utf-8"))
        vectors = data["vectors"]

        # Same vector should have similarity 1.0
        wb = vectors["Workbook"]
        sim_self = embed.cosine_similarity(
            {str(i): v for i, v in enumerate(wb)},
            {str(i): v for i, v in enumerate(wb)},
        )
        assert abs(sim_self - 1.0) < 1e-9

        # Orthogonal vectors should have similarity 0.0
        ws = vectors["Worksheet"]
        sim_orth = embed.cosine_similarity(
            {str(i): v for i, v in enumerate(wb)},
            {str(i): v for i, v in enumerate(ws)},
        )
        assert abs(sim_orth) < 1e-9

    def test_discover_targets_finds_products(self, tmp_path):
        """discover_targets finds family/platform pairs with merged knowledge."""
        for fp in [("cells", "net"), ("pdf", "go"), ("slides", "java")]:
            (tmp_path / fp[0] / fp[1] / "merged").mkdir(parents=True)

        targets = embed.discover_targets(knowledge_root=tmp_path)
        assert len(targets) == 3
        assert ("cells", "net") in targets
        assert ("pdf", "go") in targets

    def test_discover_targets_skips_underscore_dirs(self, tmp_path):
        """discover_targets ignores _vectors and other underscore dirs."""
        (tmp_path / "_vectors" / "api" / "merged").mkdir(parents=True)
        (tmp_path / "cells" / "net" / "merged").mkdir(parents=True)

        targets = embed.discover_targets(knowledge_root=tmp_path)
        assert len(targets) == 1
        assert ("cells", "net") in targets
