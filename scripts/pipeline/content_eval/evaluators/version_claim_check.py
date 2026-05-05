"""Version claim evaluator — detects prose version claims and cross-references
against the knowledge model's runtime_requirement.

Flags prose lines that state a runtime version (e.g., "Java 11", "Python 3.6",
".NET 9.0") when the knowledge model specifies a different requirement.

Category: VC (Version Claim)
"""

from __future__ import annotations

import re
from pathlib import Path
from typing import Any

import yaml

from ..models import Finding, Page
from . import BaseEvaluator

try:
    import sys as _sys
    from pathlib import Path as _Path
    _scripts = _Path(__file__).resolve().parent.parent.parent.parent
    if str(_scripts) not in _sys.path:
        _sys.path.insert(0, str(_scripts))
    from config_loader import resolve_knowledge_root as _rkr
    KNOWLEDGE_ROOT = _rkr()
except Exception:
    KNOWLEDGE_ROOT = Path("knowledge")

# ---------------------------------------------------------------------------
# Version detection regex — matches runtime version mentions in prose
# ---------------------------------------------------------------------------

# Java / JDK patterns: "Java 11", "JDK 17", "JDK 21+"
_JAVA_VERSION_RE = re.compile(
    r"\b(?:Java|JDK|JRE)\s+(\d+)(?:\.\d+)?\s*(?:\+|or\s+(?:later|above|higher))?",
    re.IGNORECASE,
)

# .NET patterns: ".NET 9.0", ".NET Framework 4.8", "net8.0"
_DOTNET_VERSION_RE = re.compile(
    r"(?:\.NET|dotnet)\s*(?:Framework\s+)?(\d+(?:\.\d+)?)\b",
    re.IGNORECASE,
)

# Python patterns: "Python 3.6", "Python 3.10+"
_PYTHON_VERSION_RE = re.compile(
    r"\bPython\s+(\d+\.\d+)\s*(?:\+|or\s+(?:later|above|higher))?",
    re.IGNORECASE,
)

# CMake patterns: "CMake 3.20+"
_CMAKE_VERSION_RE = re.compile(
    r"\bCMake\s+(\d+(?:\.\d+)?)\s*\+?",
    re.IGNORECASE,
)

# Negation context — skip lines that say "does not require" etc.
_NEGATION_RE = re.compile(
    r"\b(?:not|no\s+longer|without|don'?t|doesn'?t|removed|deprecated)\b",
    re.IGNORECASE,
)

# Severity by subdomain
_SEVERITY: dict[str, str] = {
    "reference": "FAIL",
    "products": "FAIL",
    "kb": "WARN",
    "blog": "WARN",
    "docs": "WARN",
}


def _load_runtime_requirement(family: str, platform: str) -> str:
    """Load runtime_requirement from scout/model.yaml (not in merged/)."""
    for subdir in ("scout", "merged"):
        path = KNOWLEDGE_ROOT / family / platform / subdir / "model.yaml"
        if path.exists():
            try:
                data = yaml.safe_load(path.read_text(encoding="utf-8")) or {}
                req = data.get("runtime_requirement", "")
                if req:
                    return str(req)
            except (yaml.YAMLError, OSError):
                continue
    return ""


def _extract_major_version(version_str: str) -> float | None:
    """Extract the major (or major.minor) version number from a string."""
    m = re.search(r"(\d+(?:\.\d+)?)", version_str)
    if m:
        return float(m.group(1))
    return None


def _platform_regex(platform: str) -> re.Pattern | None:
    """Return the version regex for a given platform."""
    if platform in ("java", "kotlin"):
        return _JAVA_VERSION_RE
    if platform in ("net", "dotnet"):
        return _DOTNET_VERSION_RE
    if platform == "python":
        return _PYTHON_VERSION_RE
    if platform == "cpp":
        return _CMAKE_VERSION_RE
    return None


def _extract_scannable_lines(page: Page) -> list[tuple[int, str]]:
    """Extract all scannable text lines from a page.

    Includes both prose_lines (body text) and text content embedded in
    frontmatter fields (overview.content, content.block[].content_left/right,
    plugin_description, head_description, description). This covers products
    pages where all content is in YAML frontmatter.
    """
    lines = list(page.prose_lines)

    # Extract text from frontmatter content fields
    fm = page.frontmatter
    text_fields: list[str] = []

    # Top-level description fields
    for key in ("plugin_description", "head_description", "description"):
        val = fm.get(key)
        if isinstance(val, str) and val:
            text_fields.append(val)

    # overview.content
    overview = fm.get("overview")
    if isinstance(overview, dict):
        oc = overview.get("content")
        if isinstance(oc, str) and oc:
            text_fields.append(oc)

    # content.block[].content_left / content_right
    content_section = fm.get("content")
    if isinstance(content_section, dict):
        blocks = content_section.get("block", [])
        if isinstance(blocks, list):
            for block in blocks:
                if isinstance(block, dict):
                    for side in ("content_left", "content_right"):
                        val = block.get(side)
                        if isinstance(val, str) and val:
                            text_fields.append(val)

    # single.block[].content
    single = fm.get("single")
    if isinstance(single, dict):
        blocks = single.get("block", [])
        if isinstance(blocks, list):
            for block in blocks:
                if isinstance(block, dict):
                    val = block.get("content")
                    if isinstance(val, str) and val:
                        text_fields.append(val)

    # Split frontmatter text into lines (use line_no=0 for frontmatter)
    for text in text_fields:
        for raw_line in text.splitlines():
            stripped = raw_line.strip()
            if stripped and not stripped.startswith("#"):
                lines.append((0, stripped))

    return lines


class VersionClaimCheckEvaluator(BaseEvaluator):
    name = "version_claim_check"

    def evaluate(self, page: Page, knowledge: Any) -> list[Finding]:
        if not page.family or not page.platform:
            return []

        runtime_req = _load_runtime_requirement(page.family, page.platform)
        if not runtime_req:
            return []

        req_version = _extract_major_version(runtime_req)
        if req_version is None:
            return []

        regex = _platform_regex(page.platform)
        if regex is None:
            return []

        level = _SEVERITY.get(page.subdomain, "WARN")
        findings: list[Finding] = []

        for line_no, text in _extract_scannable_lines(page):
            # Skip negation context
            if _NEGATION_RE.search(text):
                continue

            for m in regex.finditer(text):
                claimed_str = m.group(1)
                claimed_version = _extract_major_version(claimed_str)
                if claimed_version is None:
                    continue

                # Flag if claimed version differs from actual requirement
                if claimed_version != req_version:
                    findings.append(Finding(
                        level=level,
                        category="VC",
                        filepath=str(page.filepath),
                        line_no=line_no,
                        message=(
                            f"Version claim '{m.group(0).strip()}' does not match "
                            f"runtime requirement '{runtime_req}' from knowledge model"
                        ),
                        suggestion=(
                            f"Update to reflect actual requirement: {runtime_req}"
                        ),
                        evaluator=self.name,
                    ))

        return findings
