"""Candidate Repair — deterministic fixes for REPAIR_REQUIRED candidates.

Applies automated repairs for common gate failures:
  - Missing metadata keys → inject from context
  - draft/shadow_candidate not true → set to true
  - Missing sections → insert section stubs
  - Forbidden terms → remove/replace
  - Low word count → flag (cannot auto-fix without LLM)

Repairs are deterministic (no LLM). If a repair is not possible
deterministically, the candidate stays REPAIR_REQUIRED for human review.

Public API:
    RepairAction    — single repair applied
    RepairResult    — per-candidate repair outcome
    repair_candidate — attempt to repair one candidate
    repair_candidates_dir — batch repair a directory
"""
from __future__ import annotations

import re
from dataclasses import asdict, dataclass, field
from pathlib import Path
from typing import Any

from lib.content_quality import (
    FORBIDDEN_TERMS,
    REQUIRED_METADATA_KEYS,
    score_candidate,
)
from lib.schema_validators import REQUIRED_SECTIONS_BY_TYPE

REPAIR_VERSION = "1.0.0"
MAX_REPAIR_PASSES = 3


@dataclass
class RepairAction:
    """Record of a single repair applied."""
    gate_id: str
    action: str
    detail: str = ""


@dataclass
class RepairResult:
    """Outcome of repairing a candidate."""
    candidate_path: str
    repaired: bool = False
    actions: list[RepairAction] = field(default_factory=list)
    remaining_failures: list[str] = field(default_factory=list)
    passes: int = 0
    original_content: str = ""
    repaired_content: str = ""

    def to_dict(self) -> dict[str, Any]:
        d = asdict(self)
        del d["original_content"]
        del d["repaired_content"]
        return d


def _inject_metadata(content: str, key: str, value: str) -> str:
    """Inject a metadata key into frontmatter."""
    if not content.startswith("---"):
        content = f"---\n{key}: {value}\n---\n{content}"
        return content
    parts = content.split("---", 2)
    if len(parts) < 3:
        return content
    fm = parts[1].rstrip("\n")
    if f"\n{key}:" not in f"\n{fm}":
        fm = fm + f"\n{key}: {value}"
    parts[1] = fm + "\n"
    return "---".join(parts)


def _set_metadata(content: str, key: str, value: str) -> str:
    """Set a metadata key to a specific value in frontmatter."""
    if not content.startswith("---"):
        return content
    parts = content.split("---", 2)
    if len(parts) < 3:
        return content
    lines = parts[1].strip().splitlines()
    new_lines = []
    found = False
    for line in lines:
        if line.strip().startswith(f"{key}:"):
            new_lines.append(f"{key}: {value}")
            found = True
        else:
            new_lines.append(line)
    if not found:
        new_lines.append(f"{key}: {value}")
    parts[1] = "\n" + "\n".join(new_lines) + "\n"
    return "---".join(parts)


def _insert_section(content: str, section_name: str) -> str:
    """Insert a missing section heading at the end of the body."""
    stub = f"\n\n## {section_name}\n\n<!-- TODO: Section content needed -->\n"
    return content.rstrip() + stub


def _remove_forbidden_terms(content: str) -> str:
    """Remove or replace forbidden terms in body text."""
    if not content.startswith("---"):
        return content
    parts = content.split("---", 2)
    if len(parts) < 3:
        return content
    body = parts[2]
    for term in FORBIDDEN_TERMS:
        pattern = re.compile(re.escape(term), re.IGNORECASE)
        body = pattern.sub("", body)
    parts[2] = body
    return "---".join(parts)


def repair_candidate(
    content: str,
    candidate_path: str = "",
    page_type: str = "reference",
    family: str = "",
    platform: str = "",
) -> RepairResult:
    """Attempt deterministic repairs on a candidate.

    Runs up to MAX_REPAIR_PASSES, re-scoring after each pass.
    Returns RepairResult with actions taken and final content.
    """
    result = RepairResult(
        candidate_path=candidate_path,
        original_content=content,
    )

    current = content
    for pass_num in range(MAX_REPAIR_PASSES):
        score = score_candidate(current, candidate_path, page_type)
        if score.passed:
            result.repaired = True
            result.repaired_content = current
            result.passes = pass_num + 1
            return result

        made_change = False
        for gate in score.gates:
            if gate.passed:
                continue

            if gate.gate_id == "metadata_complete":
                defaults = {
                    "title": f'"{family} {platform} {page_type}"',
                    "draft": "true",
                    "shadow_candidate": "true",
                    "generator_version": "1.0.0",
                    "family": family,
                    "platform": platform,
                }
                fm_section = current.split("---", 2)[1] if "---" in current else ""
                for key in REQUIRED_METADATA_KEYS:
                    if f"{key}:" not in fm_section:
                        current = _inject_metadata(current, key, defaults.get(key, ""))
                        result.actions.append(RepairAction(
                            gate_id="metadata_complete",
                            action="inject_metadata",
                            detail=f"added {key}",
                        ))
                        made_change = True

            elif gate.gate_id == "draft_true":
                current = _set_metadata(current, "draft", "true")
                result.actions.append(RepairAction(
                    gate_id="draft_true", action="set_draft_true",
                ))
                made_change = True

            elif gate.gate_id == "shadow_marker":
                current = _set_metadata(current, "shadow_candidate", "true")
                result.actions.append(RepairAction(
                    gate_id="shadow_marker", action="set_shadow_candidate_true",
                ))
                made_change = True

            elif gate.gate_id == "no_forbidden_terms":
                current = _remove_forbidden_terms(current)
                result.actions.append(RepairAction(
                    gate_id="no_forbidden_terms", action="remove_forbidden_terms",
                ))
                made_change = True

            elif gate.gate_id == "has_sections":
                required = REQUIRED_SECTIONS_BY_TYPE.get(page_type, ["Overview"])
                for sec in required[:1]:
                    current = _insert_section(current, sec)
                    result.actions.append(RepairAction(
                        gate_id="has_sections", action="insert_section",
                        detail=f"added ## {sec}",
                    ))
                made_change = True

            elif gate.gate_id == "min_word_count":
                result.remaining_failures.append("min_word_count")

            elif gate.gate_id == "has_fact_refs":
                result.remaining_failures.append("has_fact_refs")

        if not made_change:
            break

    final_score = score_candidate(current, candidate_path, page_type)
    result.repaired = final_score.passed
    result.repaired_content = current
    result.passes = MAX_REPAIR_PASSES
    result.remaining_failures = [g.gate_id for g in final_score.gates if not g.passed]

    return result


def repair_candidates_dir(
    candidates_dir: Path,
    page_type_map: dict[str, str] | None = None,
    family: str = "",
    platform: str = "",
    write_back: bool = False,
) -> list[RepairResult]:
    """Attempt repairs on all candidates in a directory.

    Args:
        candidates_dir: Directory with .md candidates.
        page_type_map: Optional filename -> page_type mapping.
        family: Product family.
        platform: Platform.
        write_back: If True, overwrite candidate files with repaired content.

    Returns list of RepairResult objects.
    """
    results: list[RepairResult] = []
    if not candidates_dir.exists():
        return results

    for md_file in sorted(candidates_dir.glob("*.md")):
        content = md_file.read_text(encoding="utf-8")
        pt = "reference"
        if page_type_map:
            pt = page_type_map.get(md_file.name, "reference")

        result = repair_candidate(content, md_file.name, pt, family, platform)
        results.append(result)

        if write_back and result.repaired and result.repaired_content != result.original_content:
            md_file.write_text(result.repaired_content, encoding="utf-8")

    return results
