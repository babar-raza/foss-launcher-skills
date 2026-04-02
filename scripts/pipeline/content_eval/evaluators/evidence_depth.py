"""Evidence depth evaluator — assesses claim-to-evidence backing ratio."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from ..config import PLATFORM_EXPECTED_LANGS
from ..models import Finding, Page
from . import BaseEvaluator

KNOWLEDGE_ROOT = Path("knowledge")


def _api_eligible_blocks(blocks: list, platform: str) -> list:
    """Return blocks whose language tag is a known API-bearing language for this platform.

    Uses PLATFORM_EXPECTED_LANGS as the single source of truth.  Only blocks
    explicitly recognised as the platform's API language(s) are counted.
    Blocks tagged as bash, text, output, json, config, untagged, or any other
    non-API language are excluded by default — they contain no extractable API
    tokens and attach_evidence.py correctly skips them.

    If *platform* is unknown (not in PLATFORM_EXPECTED_LANGS) the function
    returns an empty list, which is the conservative safe default: no false
    positives for platforms we don't yet recognise.
    """
    eligible_langs = PLATFORM_EXPECTED_LANGS.get(platform, set())
    # NOTE: "" (untagged blocks) is intentionally excluded here even though
    # token_ops._is_target_lang includes "" for all platforms.  The two functions
    # serve different concerns: token_ops is a conservative *extractor* that must
    # not silently drop real API code from untagged blocks; this function is an
    # *evaluator* guard that must not emit false-positive WARNs for untagged
    # output/prose blocks.  The net behaviour is correct in both directions.
    return [cb for cb in blocks if cb.lang.lower() in eligible_langs]


class EvidenceDepthEvaluator(BaseEvaluator):
    """Assesses whether evidence backing is sufficient for content claims.

    Checks:
    - Evidence block is present
    - Claim density (factual prose lines vs evidence citations)
    - API coverage (tokens in code vs evidence.apis)
    - Stale evidence (model_sha mismatch)
    - Per-section coverage via evidence.sections (if present)
    """

    name = "evidence_depth"

    def evaluate(self, page: Page, knowledge: Any) -> list[Finding]:
        findings: list[Finding] = []
        fm = page.frontmatter
        evidence = fm.get("evidence", {})

        if not evidence:
            if _api_eligible_blocks(page.code_blocks, page.platform) or len(page.prose_lines) > 10:
                findings.append(Finding(
                    level="WARN",
                    category="EG",
                    filepath=str(page.filepath),
                    line_no=1,
                    message="No evidence block in frontmatter",
                    suggestion="Run attach_evidence.py to generate evidence citations",
                    evaluator=self.name,
                ))
            return findings

        # Check claim count
        claims = evidence.get("claims", [])
        apis = evidence.get("apis", [])

        # Count factual prose lines (lines with backtick-wrapped identifiers)
        factual_lines = sum(1 for _, text in page.prose_lines if "`" in text)

        # Only count blocks in the platform's expected API-bearing languages.
        # PLATFORM_EXPECTED_LANGS is the single source of truth: bash, text,
        # output, config, untagged, and any other non-API language are excluded
        # because attach_evidence.py correctly skips them.
        eligible = _api_eligible_blocks(page.code_blocks, page.platform)
        code_block_count = len(eligible)

        # Warn if API-language code blocks are present but no evidence APIs cited
        if code_block_count >= 2 and len(apis) == 0:
            findings.append(Finding(
                level="WARN",
                category="EG",
                filepath=str(page.filepath),
                line_no=1,
                message=f"Page has {code_block_count} API-eligible code blocks but 0 evidence APIs",
                suggestion="Run attach_evidence.py to map code tokens to evidence",
                evaluator=self.name,
            ))

        # Warn if substantial content but no claims
        if factual_lines > 5 and len(claims) == 0 and len(apis) == 0:
            findings.append(Finding(
                level="INFO",
                category="EG",
                filepath=str(page.filepath),
                line_no=1,
                message=f"Page has {factual_lines} factual lines but empty evidence block",
                suggestion="Review whether claims.json mappings need improvement",
                evaluator=self.name,
            ))

        # Check model_sha staleness
        model_sha = evidence.get("model_sha", "")
        current_sha = ""
        if model_sha and page.family and page.platform:
            model_path = KNOWLEDGE_ROOT / page.family / page.platform / "merged" / "model.yaml"
            if model_path.exists():
                import yaml
                try:
                    model = yaml.safe_load(model_path.read_text(encoding="utf-8"))
                    current_sha = model.get("repo_sha", "")
                    if current_sha and model_sha != current_sha:
                        findings.append(Finding(
                            level="WARN",
                            category="EG",
                            filepath=str(page.filepath),
                            line_no=1,
                            message="Evidence stale: model_sha does not match current knowledge",
                            suggestion="Rerun attach_evidence.py to update evidence block",
                            evaluator=self.name,
                        ))
                except Exception:
                    pass

        # --- Per-section evidence checks ---
        sections = evidence.get("sections", [])
        if sections:
            findings.extend(
                self._evaluate_sections(page, evidence, sections, current_sha)
            )

        return findings

    def _evaluate_sections(
        self, page: Page, evidence: dict, sections: list, current_sha: str
    ) -> list[Finding]:
        """Evaluate per-section evidence coverage."""
        findings: list[Finding] = []

        # Build a map of heading line → section entry for quick lookup
        section_by_line = {s.get("line", 0): s for s in sections}

        # Build a map of which page headings have code blocks after them
        headings_with_code = self._headings_with_code(page)

        # Check: sections with code blocks but empty apis
        for sec in sections:
            heading = sec.get("heading", "")
            line = sec.get("line", 0)
            sec_apis = sec.get("apis", [])
            sec_claims = sec.get("claims", [])

            # Check if this section's heading corresponds to one that has code blocks
            if line in headings_with_code and not sec_apis:
                findings.append(Finding(
                    level="WARN",
                    category="EG",
                    filepath=str(page.filepath),
                    line_no=line,
                    message=f"Section \"{heading}\" has code blocks but 0 evidence APIs",
                    suggestion="Check token extraction or claims.json mapping for this section",
                    evaluator=self.name,
                ))

        # Check: sections data staleness (model_sha mismatch)
        model_sha = evidence.get("model_sha", "")
        if current_sha and model_sha and model_sha != current_sha:
            findings.append(Finding(
                level="WARN",
                category="EG",
                filepath=str(page.filepath),
                line_no=1,
                message="Section-level evidence is stale: model_sha mismatch",
                suggestion="Rerun attach_evidence.py to regenerate sections data",
                evaluator=self.name,
            ))

        # INFO: section-level coverage statistics
        total_sections_on_page = len(page.headings)
        covered_sections = len(sections)
        total_section_apis = sum(len(s.get("apis", [])) for s in sections)
        total_section_claims = sum(len(s.get("claims", [])) for s in sections)

        if total_sections_on_page > 0:
            coverage_pct = round(covered_sections / total_sections_on_page * 100)
        else:
            coverage_pct = 0

        findings.append(Finding(
            level="INFO",
            category="EG",
            filepath=str(page.filepath),
            line_no=1,
            message=(
                f"Section evidence: {covered_sections}/{total_sections_on_page} sections covered "
                f"({coverage_pct}%), {total_section_apis} APIs, {total_section_claims} claims"
            ),
            suggestion="",
            evaluator=self.name,
        ))

        return findings

    def _headings_with_code(self, page: Page) -> set[int]:
        """Return set of heading line numbers that have code blocks in their section.

        A code block belongs to a heading if it appears between that heading
        and the next heading of same or higher level.
        """
        result = set()
        if not page.headings:
            return result

        # Build (heading_line, heading_level) pairs, sorted by line
        heading_info = sorted(
            [(h.line_no, h.level) for h in page.headings],
            key=lambda x: x[0],
        )

        for i, (h_line, h_level) in enumerate(heading_info):
            # Find end of this section: next heading of same or higher level
            if i + 1 < len(heading_info):
                section_end = heading_info[i + 1][0]
            else:
                # Extends to end of file
                section_end = float("inf")

            # Check if any API-eligible code block starts within this section
            eligible_langs = PLATFORM_EXPECTED_LANGS.get(page.platform, set())
            for cb in page.code_blocks:
                if h_line < cb.start_line < section_end and cb.lang.lower() in eligible_langs:
                    result.add(h_line)
                    break

        return result
