"""Tests for lib/fact_graph.py — schema validation, determinism, missing input handling."""
from __future__ import annotations

import hashlib
import json
import tempfile
from pathlib import Path

import pytest

import sys
_PIPELINE_ROOT = Path(__file__).resolve().parents[1] / "scripts" / "pipeline"
if str(_PIPELINE_ROOT) not in sys.path:
    sys.path.insert(0, str(_PIPELINE_ROOT))

from lib.fact_graph import (
    FACT_GRAPH_SCHEMA_VERSION,
    Fact,
    FactGraph,
    FactType,
    VerificationStatus,
    compile_fact_graph,
)


# ---------------------------------------------------------------------------
# Fact ID stability
# ---------------------------------------------------------------------------

class TestFactId:
    def test_deterministic_id(self):
        id1 = Fact.make_id("pdf", "go", "source", "api_class", "Document")
        id2 = Fact.make_id("pdf", "go", "source", "api_class", "Document")
        assert id1 == id2

    def test_different_inputs_different_id(self):
        id1 = Fact.make_id("pdf", "go", "source", "api_class", "Document")
        id2 = Fact.make_id("pdf", "go", "source", "api_class", "Page")
        assert id1 != id2

    def test_id_format(self):
        fid = Fact.make_id("pdf", "go", "source", "api_class", "Document")
        assert fid.startswith("FG-")
        assert len(fid) == 15  # "FG-" + 12 hex chars


# ---------------------------------------------------------------------------
# FactGraph serialization
# ---------------------------------------------------------------------------

class TestFactGraphSerialization:
    def _make_graph(self) -> FactGraph:
        graph = FactGraph(family="pdf", platform="go", repo_sha="abc123", compiled_from="merged")
        graph.add_fact(Fact(
            fact_id=Fact.make_id("pdf", "go", "source", "api_class", "Document"),
            fact_type=FactType.SOURCE.value,
            category="api_class",
            family="pdf",
            platform="go",
            text="Document",
            repo_sha="abc123",
        ))
        graph.add_fact(Fact(
            fact_id=Fact.make_id("pdf", "go", "source", "api_method", "Document.Save"),
            fact_type=FactType.SOURCE.value,
            category="api_method",
            family="pdf",
            platform="go",
            text="Document.Save",
            repo_sha="abc123",
        ))
        return graph

    def test_to_dict_structure(self):
        graph = self._make_graph()
        d = graph.to_dict()
        assert d["schema_version"] == FACT_GRAPH_SCHEMA_VERSION
        assert d["family"] == "pdf"
        assert d["platform"] == "go"
        assert d["fact_count"] == 2
        assert len(d["facts"]) == 2

    def test_deterministic_json(self):
        """Two serializations of the same graph must produce identical JSON."""
        g1 = self._make_graph()
        g2 = self._make_graph()
        assert g1.to_json() == g2.to_json()

    def test_deterministic_sha256(self):
        """SHA256 of two independent serializations must match."""
        g1 = self._make_graph()
        g2 = self._make_graph()
        h1 = hashlib.sha256(g1.to_json().encode()).hexdigest()
        h2 = hashlib.sha256(g2.to_json().encode()).hexdigest()
        assert h1 == h2

    def test_roundtrip(self):
        graph = self._make_graph()
        json_str = graph.to_json()
        restored = FactGraph.from_json(json_str)
        assert restored.family == "pdf"
        assert restored.fact_count == 2
        assert restored.facts[0].text in ("Document", "Document.Save")

    def test_write_and_read(self, tmp_path):
        graph = self._make_graph()
        path = tmp_path / "fact_graph.json"
        graph.write(path)
        restored = FactGraph.read(path)
        assert restored.to_json() == graph.to_json()

    def test_sorted_output(self):
        """Facts should be sorted by (category, fact_type, fact_id)."""
        graph = FactGraph(family="test", platform="test")
        graph.add_fact(Fact(
            fact_id="FG-zzz", fact_type="source", category="format",
            family="test", platform="test", text="z",
        ))
        graph.add_fact(Fact(
            fact_id="FG-aaa", fact_type="source", category="api_class",
            family="test", platform="test", text="a",
        ))
        d = graph.to_dict()
        cats = [f["category"] for f in d["facts"]]
        assert cats == ["api_class", "format"]


# ---------------------------------------------------------------------------
# compile_fact_graph
# ---------------------------------------------------------------------------

class TestCompileFactGraph:
    def _setup_merged(self, root: Path, family: str, platform: str) -> Path:
        merged = root / family / platform / "merged"
        merged.mkdir(parents=True)

        # model.yaml
        (merged / "model.yaml").write_text(
            "repo_sha: deadbeef\nversion: '25.1'\n", encoding="utf-8"
        )

        # api_surface.json
        api = {
            "classes": [
                {
                    "name": "Document",
                    "methods": [
                        {"name": "Save", "params": ["path"]},
                        {"name": "Close", "params": []},
                    ],
                }
            ]
        }
        (merged / "api_surface.json").write_text(
            json.dumps(api), encoding="utf-8"
        )

        # claims.json
        claims = {
            "claims": [
                {"claim_id": "CLM-001", "text": "Supports PDF/A"},
                {"claim_id": "ERC-001", "text": "High performance rendering"},
            ]
        }
        (merged / "claims.json").write_text(
            json.dumps(claims), encoding="utf-8"
        )

        # formats.json
        formats = {
            "formats": [
                {"extension": ".pdf", "support": "read_write"},
                {"extension": ".docx", "support": "read"},
            ]
        }
        (merged / "formats.json").write_text(
            json.dumps(formats), encoding="utf-8"
        )

        return root

    def test_compile_basic(self, tmp_path):
        root = self._setup_merged(tmp_path, "pdf", "go")
        graph = compile_fact_graph("pdf", "go", root)
        assert graph.family == "pdf"
        assert graph.platform == "go"
        assert graph.repo_sha == "deadbeef"
        assert graph.fact_count > 0

    def test_compile_fact_categories(self, tmp_path):
        root = self._setup_merged(tmp_path, "pdf", "go")
        graph = compile_fact_graph("pdf", "go", root)
        cats = {f.category for f in graph.facts}
        assert "api_class" in cats
        assert "api_method" in cats
        assert "claim" in cats
        assert "format" in cats

    def test_compile_class_and_methods(self, tmp_path):
        root = self._setup_merged(tmp_path, "pdf", "go")
        graph = compile_fact_graph("pdf", "go", root)
        classes = [f for f in graph.facts if f.category == "api_class"]
        methods = [f for f in graph.facts if f.category == "api_method"]
        assert len(classes) == 1
        assert classes[0].text == "Document"
        assert len(methods) == 2
        method_texts = {m.text for m in methods}
        assert "Document.Save" in method_texts
        assert "Document.Close" in method_texts

    def test_compile_claims(self, tmp_path):
        root = self._setup_merged(tmp_path, "pdf", "go")
        graph = compile_fact_graph("pdf", "go", root)
        claims = [f for f in graph.facts if f.category == "claim"]
        assert len(claims) == 2
        # CLM- claims should be SOURCE, ERC- claims should be INFERRED
        clm = [c for c in claims if "PDF/A" in c.text][0]
        erc = [c for c in claims if "rendering" in c.text][0]
        assert clm.fact_type == FactType.SOURCE.value
        assert erc.fact_type == FactType.INFERRED.value

    def test_compile_formats(self, tmp_path):
        root = self._setup_merged(tmp_path, "pdf", "go")
        graph = compile_fact_graph("pdf", "go", root)
        formats = [f for f in graph.facts if f.category == "format"]
        assert len(formats) == 2

    def test_compile_determinism(self, tmp_path):
        """Two compilations from the same artifacts must produce identical output."""
        root = self._setup_merged(tmp_path, "pdf", "go")
        g1 = compile_fact_graph("pdf", "go", root)
        g2 = compile_fact_graph("pdf", "go", root)
        h1 = hashlib.sha256(g1.to_json().encode()).hexdigest()
        h2 = hashlib.sha256(g2.to_json().encode()).hexdigest()
        assert h1 == h2

    def test_compile_missing_merged(self, tmp_path):
        with pytest.raises(FileNotFoundError):
            compile_fact_graph("nonexistent", "nope", tmp_path)

    def test_compile_missing_optional_files(self, tmp_path):
        """Should succeed with only model.yaml present."""
        merged = tmp_path / "pdf" / "go" / "merged"
        merged.mkdir(parents=True)
        (merged / "model.yaml").write_text("repo_sha: abc\n", encoding="utf-8")
        graph = compile_fact_graph("pdf", "go", tmp_path)
        assert graph.fact_count == 0
        assert graph.repo_sha == "abc"


# ---------------------------------------------------------------------------
# Enum coverage
# ---------------------------------------------------------------------------

class TestEnums:
    def test_fact_types(self):
        assert set(FactType) == {FactType.SOURCE, FactType.INFERRED, FactType.EXTERNAL, FactType.MANUAL}

    def test_verification_statuses(self):
        assert set(VerificationStatus) == {
            VerificationStatus.VERIFIED, VerificationStatus.UNVERIFIED,
            VerificationStatus.REJECTED, VerificationStatus.STALE,
        }
