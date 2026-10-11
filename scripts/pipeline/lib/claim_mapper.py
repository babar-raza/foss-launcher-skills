"""Claim Mapper — map and verify fact references in generated content.

Reads generated markdown candidates and maps fact_ref comments and
provenance_fact_ids to a FactGraph. Detects unsupported references.

Public API:
    extract_fact_refs    — extract fact IDs from markdown content
    build_claim_map      — map all references to fact graph facts
    verify_claim_map     — verify all references are supported
    ClaimMap             — structured claim map with serialization
"""
from __future__ import annotations

import json
import re
from dataclasses import asdict, dataclass, field
from pathlib import Path
from typing import Any

CLAIM_MAP_SCHEMA_VERSION = "1.0.0"

# Pattern to match <!-- fact_ref: FG-xxxxxxxxxxxx -->
_FACT_REF_RE = re.compile(r'<!--\s*fact_ref:\s*(FG-[a-f0-9]{12})\s*-->')
# Pattern to match fact IDs in frontmatter provenance_fact_ids
_PROV_RE = re.compile(r'"(FG-[a-f0-9]{12})"')


def extract_fact_refs(content: str) -> list[str]:
    """Extract all fact_ref IDs from markdown content."""
    refs = set()
    refs.update(_FACT_REF_RE.findall(content))
    refs.update(_PROV_RE.findall(content))
    return sorted(refs)


def extract_api_symbols(content: str) -> list[str]:
    """Extract API class/method symbol names from backtick references.

    Only matches dotted names like `ClassName.MethodName` to avoid
    false positives on standalone CamelCase words in prose.
    """
    symbols = re.findall(r'`([A-Z][a-zA-Z0-9]*\.[A-Z][a-zA-Z0-9]*)`', content)
    return sorted(set(symbols))


@dataclass
class ClaimMapEntry:
    """Single claim mapping entry."""
    fact_id: str
    found_in_graph: bool
    fact_type: str = ""
    category: str = ""
    text: str = ""
    source_file: str = ""


@dataclass
class ClaimMap:
    """Structured claim map for a candidate."""
    schema_version: str = CLAIM_MAP_SCHEMA_VERSION
    candidate_path: str = ""
    family: str = ""
    platform: str = ""
    total_refs: int = 0
    supported_refs: int = 0
    unsupported_refs: int = 0
    entries: list[ClaimMapEntry] = field(default_factory=list)
    api_symbols: list[str] = field(default_factory=list)
    unsupported_symbols: list[str] = field(default_factory=list)

    @property
    def is_valid(self) -> bool:
        """A claim map is valid if all fact refs are supported."""
        return self.unsupported_refs == 0 and len(self.unsupported_symbols) == 0

    def to_dict(self) -> dict[str, Any]:
        return {
            "schema_version": self.schema_version,
            "candidate_path": self.candidate_path,
            "family": self.family,
            "platform": self.platform,
            "total_refs": self.total_refs,
            "supported_refs": self.supported_refs,
            "unsupported_refs": self.unsupported_refs,
            "is_valid": self.is_valid,
            "entries": [asdict(e) for e in self.entries],
            "api_symbols": self.api_symbols,
            "unsupported_symbols": self.unsupported_symbols,
        }

    def to_json(self, indent: int = 2) -> str:
        return json.dumps(self.to_dict(), indent=indent, ensure_ascii=False)

    def write(self, path: Path) -> None:
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(self.to_json(), encoding="utf-8")


def build_claim_map(
    content: str,
    fact_index: dict[str, dict],
    candidate_path: str = "",
    family: str = "",
    platform: str = "",
) -> ClaimMap:
    """Build a claim map from content and fact index.

    Args:
        content: Markdown content string
        fact_index: dict mapping fact_id -> fact data dict
        candidate_path: Path to the candidate file
        family: Product family
        platform: Platform
    """
    fact_refs = extract_fact_refs(content)
    api_symbols = extract_api_symbols(content)

    entries = []
    supported = 0
    unsupported = 0

    for fid in fact_refs:
        if fid in fact_index:
            fact = fact_index[fid]
            entries.append(ClaimMapEntry(
                fact_id=fid,
                found_in_graph=True,
                fact_type=fact.get("fact_type", ""),
                category=fact.get("category", ""),
                text=fact.get("text", ""),
            ))
            supported += 1
        else:
            entries.append(ClaimMapEntry(
                fact_id=fid,
                found_in_graph=False,
            ))
            unsupported += 1

    # Check API symbols against fact graph texts
    known_symbols = {f.get("text", "") for f in fact_index.values()
                     if f.get("category") in ("api_class", "api_method")}
    unsupported_symbols = [s for s in api_symbols if s not in known_symbols]

    return ClaimMap(
        candidate_path=candidate_path,
        family=family,
        platform=platform,
        total_refs=len(fact_refs),
        supported_refs=supported,
        unsupported_refs=unsupported,
        entries=entries,
        api_symbols=api_symbols,
        unsupported_symbols=unsupported_symbols,
    )


def verify_candidates(
    candidate_dir: Path,
    fact_index: dict[str, dict],
    family: str = "",
    platform: str = "",
) -> dict[str, Any]:
    """Verify all candidates in a directory.

    Returns a verification report dict.
    """
    results = []
    total_pass = 0
    total_fail = 0

    for md_file in sorted(candidate_dir.glob("*.md")):
        content = md_file.read_text(encoding="utf-8")
        claim_map = build_claim_map(content, fact_index, str(md_file), family, platform)

        status = "PASS" if claim_map.is_valid else "FAIL"
        if status == "PASS":
            total_pass += 1
        else:
            total_fail += 1

        results.append({
            "candidate": md_file.name,
            "status": status,
            "total_refs": claim_map.total_refs,
            "supported_refs": claim_map.supported_refs,
            "unsupported_refs": claim_map.unsupported_refs,
            "unsupported_symbols": claim_map.unsupported_symbols,
        })

    return {
        "schema_version": CLAIM_MAP_SCHEMA_VERSION,
        "family": family,
        "platform": platform,
        "candidates_checked": len(results),
        "passed": total_pass,
        "failed": total_fail,
        "results": results,
    }


def validate_page_plan_fact_refs(plan: dict, fact_index: dict[str, dict]) -> list[str]:
    """Validate that all required_facts in a page plan exist in the fact graph.

    Returns list of error strings (empty = valid).
    """
    errors = []
    for sd_name, sd_data in plan.get("subdomains", {}).items():
        for i, page in enumerate(sd_data.get("pages", [])):
            for fid in page.get("required_facts", []):
                if fid not in fact_index:
                    errors.append(
                        f"{sd_name}.pages[{i}] ({page.get('title', '?')}): "
                        f"required fact {fid} not in fact graph"
                    )
            for fid in page.get("provenance_refs", []):
                if fid not in fact_index:
                    errors.append(
                        f"{sd_name}.pages[{i}] ({page.get('title', '?')}): "
                        f"provenance ref {fid} not in fact graph"
                    )
    return errors
