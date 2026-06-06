"""Canonical Fact Graph — normalized, versioned knowledge representation.

Provides a unified view of all facts extracted from FOSS repos, enriched claims,
and external signals. Every fact has a stable ID, provenance type, and
verification status.

Public API:
    FactType        — enum of fact provenance types
    VerificationStatus — enum of verification states
    Fact            — single knowledge fact with stable ID
    FactGraph       — collection of facts with serialization
    compile_fact_graph — build graph from existing knowledge artifacts
"""
from __future__ import annotations

import hashlib
import json
from dataclasses import asdict, dataclass, field
from enum import Enum
from pathlib import Path
from typing import Any


# Schema version — bump on breaking changes
FACT_GRAPH_SCHEMA_VERSION = "1.0.0"


class FactType(str, Enum):
    """Provenance type for a fact."""
    SOURCE = "source"          # Tree-sitter extraction (deterministic)
    INFERRED = "inferred"      # LLM enrichment
    EXTERNAL = "external"      # External tool signal (e.g. Skill Seekers)
    MANUAL = "manual"          # Human-authored


class VerificationStatus(str, Enum):
    """Verification state of a fact."""
    VERIFIED = "verified"
    UNVERIFIED = "unverified"
    REJECTED = "rejected"
    STALE = "stale"


@dataclass(frozen=True)
class Fact:
    """Single knowledge fact with stable ID and provenance."""
    fact_id: str
    fact_type: str          # FactType value
    category: str           # api_class, api_method, claim, format, ...
    family: str
    platform: str
    text: str
    source_file: str = ""
    repo_sha: str = ""
    confidence: float = 1.0
    verification_status: str = "unverified"  # VerificationStatus value
    metadata: dict = field(default_factory=dict)

    @staticmethod
    def make_id(family: str, platform: str, fact_type: str, category: str, text: str) -> str:
        """Deterministic fact ID from content hash."""
        raw = f"{family}|{platform}|{fact_type}|{category}|{text}"
        return f"FG-{hashlib.sha256(raw.encode('utf-8')).hexdigest()[:12]}"


@dataclass
class FactGraph:
    """Collection of facts with metadata and serialization."""
    schema_version: str = FACT_GRAPH_SCHEMA_VERSION
    family: str = ""
    platform: str = ""
    repo_sha: str = ""
    compiled_from: str = ""     # "merged" | "scout" | "external"
    facts: list[Fact] = field(default_factory=list)

    @property
    def fact_count(self) -> int:
        return len(self.facts)

    def add_fact(self, fact: Fact) -> None:
        self.facts.append(fact)

    def to_dict(self) -> dict[str, Any]:
        """Serialize to dict with sorted keys for determinism."""
        return {
            "schema_version": self.schema_version,
            "family": self.family,
            "platform": self.platform,
            "repo_sha": self.repo_sha,
            "compiled_from": self.compiled_from,
            "fact_count": self.fact_count,
            "facts": sorted(
                [asdict(f) for f in self.facts],
                key=lambda x: (x["category"], x["fact_type"], x["fact_id"]),
            ),
        }

    def to_json(self, indent: int = 2) -> str:
        """Deterministic JSON serialization."""
        return json.dumps(self.to_dict(), indent=indent, sort_keys=False, ensure_ascii=False)

    def write(self, path: Path) -> None:
        """Write to file."""
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(self.to_json(), encoding="utf-8")

    @classmethod
    def from_dict(cls, data: dict) -> FactGraph:
        """Deserialize from dict."""
        facts = [Fact(**f) for f in data.get("facts", [])]
        return cls(
            schema_version=data.get("schema_version", FACT_GRAPH_SCHEMA_VERSION),
            family=data.get("family", ""),
            platform=data.get("platform", ""),
            repo_sha=data.get("repo_sha", ""),
            compiled_from=data.get("compiled_from", ""),
            facts=facts,
        )

    @classmethod
    def from_json(cls, text: str) -> FactGraph:
        """Deserialize from JSON string."""
        return cls.from_dict(json.loads(text))

    @classmethod
    def read(cls, path: Path) -> FactGraph:
        """Read from file."""
        return cls.from_json(path.read_text(encoding="utf-8"))


def compile_fact_graph(
    family: str,
    platform: str,
    knowledge_root: Path | None = None,
) -> FactGraph:
    """Build a FactGraph from existing merged knowledge artifacts.

    Reads:
        - merged/model.yaml (repo SHA, version)
        - merged/api_surface.json (classes, methods)
        - merged/claims.json (enriched claims)
        - merged/formats.json (format support)

    All inputs are read-only. No knowledge artifacts are modified.
    """
    if knowledge_root is None:
        # Default: repo_root / knowledge
        knowledge_root = Path(__file__).resolve().parents[3] / "knowledge"

    merged = knowledge_root / family / platform / "merged"

    if not merged.exists():
        raise FileNotFoundError(f"Merged knowledge not found: {merged}")

    # Load model.yaml for repo SHA
    model_path = merged / "model.yaml"
    repo_sha = ""
    if model_path.exists():
        import yaml
        model = yaml.safe_load(model_path.read_text(encoding="utf-8"))
        repo_sha = model.get("repo_sha", "")

    graph = FactGraph(
        family=family,
        platform=platform,
        repo_sha=repo_sha,
        compiled_from="merged",
    )

    # --- API Surface facts ---
    api_path = merged / "api_surface.json"
    if api_path.exists():
        try:
            api_text = api_path.read_text(encoding="utf-8")
        except UnicodeDecodeError:
            api_text = api_path.read_text(encoding="utf-8", errors="replace")
        api_raw = json.loads(api_text)
        # Normalize: real files are flat lists; tests may use {"classes": [...]}
        if isinstance(api_raw, dict):
            entries = api_raw.get("classes", [])
        else:
            entries = api_raw if isinstance(api_raw, list) else []

        for entry in entries:
            name = entry.get("name", "")
            if not name:
                continue
            kind = entry.get("kind", "class")

            # Treat all class-like kinds as api_class
            # Real repos use tree-sitter node names: class_definition, class_specifier,
            # class_declaration, struct_specifier, enum_specifier, interface_declaration, etc.
            _CLASS_KINDS = {
                "class", "type_spec", "struct", "enum", "interface",
                "api_class",
                "class_definition", "class_declaration", "class_specifier",
                "struct_specifier", "struct_declaration",
                "enum_specifier", "enum_declaration",
                "interface_declaration",
                "record_declaration", "type_alias_declaration",
            }
            if kind in _CLASS_KINDS:
                graph.add_fact(Fact(
                    fact_id=Fact.make_id(family, platform, "source", "api_class", name),
                    fact_type=FactType.SOURCE.value,
                    category="api_class",
                    family=family,
                    platform=platform,
                    text=name,
                    repo_sha=repo_sha,
                    confidence=1.0,
                    verification_status=VerificationStatus.VERIFIED.value,
                ))
                # Nested methods
                for method in entry.get("methods", []):
                    method_name = method.get("name", "")
                    full_name = f"{name}.{method_name}"
                    graph.add_fact(Fact(
                        fact_id=Fact.make_id(family, platform, "source", "api_method", full_name),
                        fact_type=FactType.SOURCE.value,
                        category="api_method",
                        family=family,
                        platform=platform,
                        text=full_name,
                        repo_sha=repo_sha,
                        confidence=1.0,
                        verification_status=VerificationStatus.VERIFIED.value,
                        metadata={"params": method.get("params", [])},
                    ))
            elif kind in ("function", "api_method"):
                # Top-level function or standalone method
                graph.add_fact(Fact(
                    fact_id=Fact.make_id(family, platform, "source", "api_method", name),
                    fact_type=FactType.SOURCE.value,
                    category="api_method",
                    family=family,
                    platform=platform,
                    text=name,
                    repo_sha=repo_sha,
                    confidence=1.0,
                    verification_status=VerificationStatus.VERIFIED.value,
                    metadata={"params": entry.get("params", [])},
                ))
            elif kind == "api_field":
                # Standalone field/property entry
                graph.add_fact(Fact(
                    fact_id=Fact.make_id(family, platform, "source", "api_field", name),
                    fact_type=FactType.SOURCE.value,
                    category="api_field",
                    family=family,
                    platform=platform,
                    text=name,
                    repo_sha=repo_sha,
                    confidence=1.0,
                    verification_status=VerificationStatus.VERIFIED.value,
                ))

    # --- Claims facts ---
    claims_path = merged / "claims.json"
    if claims_path.exists():
        try:
            claims_raw = claims_path.read_text(encoding="utf-8")
        except UnicodeDecodeError:
            claims_raw = claims_path.read_text(encoding="utf-8", errors="replace")
        claims_data = json.loads(claims_raw)
        claims_list = claims_data.get("claims", claims_data) if isinstance(claims_data, dict) else claims_data
        if isinstance(claims_list, list):
            for claim in claims_list:
                claim_text = claim.get("text", claim.get("claim", ""))
                claim_id = claim.get("claim_id", "")
                if not claim_text:
                    continue
                fact_type_val = FactType.INFERRED.value if claim_id.startswith("ERC-") else FactType.SOURCE.value
                graph.add_fact(Fact(
                    fact_id=Fact.make_id(family, platform, fact_type_val, "claim", claim_text),
                    fact_type=fact_type_val,
                    category="claim",
                    family=family,
                    platform=platform,
                    text=claim_text,
                    repo_sha=repo_sha,
                    confidence=claim.get("confidence", 0.8),
                    verification_status=VerificationStatus.UNVERIFIED.value,
                    metadata={"original_claim_id": claim_id},
                ))

    # --- Format facts ---
    formats_path = merged / "formats.json"
    if formats_path.exists():
        formats_data = json.loads(formats_path.read_text(encoding="utf-8"))
        formats_list = formats_data.get("formats", formats_data) if isinstance(formats_data, dict) else formats_data
        if isinstance(formats_list, list):
            for fmt in formats_list:
                ext = fmt.get("extension", fmt.get("ext", ""))
                support = fmt.get("support", "unknown")
                if not ext:
                    continue
                text = f"format:{ext}:{support}"
                graph.add_fact(Fact(
                    fact_id=Fact.make_id(family, platform, "source", "format", text),
                    fact_type=FactType.SOURCE.value,
                    category="format",
                    family=family,
                    platform=platform,
                    text=text,
                    repo_sha=repo_sha,
                    confidence=1.0,
                    verification_status=VerificationStatus.VERIFIED.value,
                    metadata={"extension": ext, "support": support},
                ))

    return graph
