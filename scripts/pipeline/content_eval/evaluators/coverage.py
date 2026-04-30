"""Coverage evaluator — detects important missing API capabilities."""

from __future__ import annotations

import json
import re
from pathlib import Path
from typing import Any

from ..models import Finding, Page
from . import BaseEvaluator

KNOWLEDGE_ROOT = Path("knowledge")

# ---------------------------------------------------------------------------
# Platform constants for interface-page generation policy (S-Fix-5)
# ---------------------------------------------------------------------------
# Java and .NET expose interfaces as user-facing API — pages SHOULD exist.
INTERFACE_PAGE_PLATFORMS = {"net", "java"}
# C++ and Python use I-prefixed types as implementation contracts — no pages.
CONCRETE_ONLY_PLATFORMS = {"cpp", "python"}


def _is_interface_entry(name: str, kind: str) -> bool:
    """Return True if this class entry represents an abstract interface.

    Detects by:
    1. kind field set to "interface" or "abstract_class"  (populated by S-Fix-4)
    2. Name pattern: starts with "I" followed by an uppercase letter (C++ idiom)
    """
    if kind in ("interface", "abstract_class"):
        return True
    if len(name) >= 2 and name[0] == "I" and name[1].isupper():
        return True
    return False


def _compute_class_importance(entry: dict) -> float:
    """Score 0.0-1.0 based on method count, properties, tests, docs."""
    mc = entry.get("method_count", 0)
    pc = entry.get("property_count", 0)
    base = min(1.0, (mc + pc) / 20)
    if entry.get("has_tests"):
        base += 0.15
    if entry.get("has_doc"):
        base += 0.1
    # Penalize likely internal classes (only __init__)
    if mc <= 1 and pc == 0:
        base -= 0.2
    return max(0.0, min(1.0, base))


def _to_slug(name: str) -> str:
    """Convert a PascalCase class name to kebab-case filename slug.

    Examples:
        BevelPresetType  → bevel-preset-type
        IPPImage         → i-p-p-image  (kept as-is per regex split)
        FillType         → fill-type
    """
    # Insert hyphen before every uppercase letter that follows a lowercase/digit,
    # or before an uppercase run followed by a lowercase (ABCDef → abc-def).
    s = re.sub(r"([a-z0-9])([A-Z])", r"\1-\2", name)
    s = re.sub(r"([A-Z]+)([A-Z][a-z])", r"\1-\2", s)
    return s.lower()


class CoverageEvaluator(BaseEvaluator):
    """Detects important API capabilities missing from content.

    Compares classes and key methods mentioned in content against the
    knowledge model to identify coverage gaps, weighted by class importance.

    Platform-aware rules (S-Fix-5):
    - For cpp/python: I-prefixed abstract classes are filtered out of the
      "missing" set because those platforms do not generate reference pages
      for abstract interfaces.
    - For net/java: interfaces ARE user-facing and are included normally.

    Enum coverage (S-Fix-6):
    - After the main class check, a second pass scans for enum kinds in
      api_surface.json.  If ≥3 enums lack a corresponding reference page
      they are surfaced as an INFO finding.
    """

    name = "coverage"

    def evaluate(self, page: Page, knowledge: Any) -> list[Finding]:
        if not page.family or not page.platform:
            return []

        # Only check docs and reference pages for coverage
        if page.page_role not in ("docs", "reference"):
            return []

        platform = page.platform  # e.g. "cpp", "python", "dotnet", "java"

        # Use Knowledge object instead of direct filesystem reads
        if not isinstance(knowledge, object) or not getattr(knowledge, 'available', False):
            return [Finding(
                level="WARN",
                category="CG",
                filepath=str(page.filepath),
                line_no=0,
                message=(
                    f"UNVERIFIED: knowledge artifacts not available for "
                    f"{page.family}/{page.platform}. Claims cannot be validated."
                ),
                evaluator=self.name,
            )]

        all_classes = set(knowledge.classes.keys()) if knowledge.classes else set()
        if not all_classes:
            return []

        # class_importance and class_kind loaded into Knowledge from coverage_matrix.json
        class_importance: dict[str, float] = getattr(knowledge, 'class_importance', {})
        class_kind: dict[str, str] = getattr(knowledge, 'class_kind', {})

        # Extract classes mentioned in page (from code blocks and prose)
        mentioned_classes: set[str] = set()
        for block in page.code_blocks:
            for word in set(re.findall(r"\b([A-Z][A-Za-z0-9]+)\b", block.content)):
                mentioned_classes.add(word)
        for _, line in page.prose_lines:
            for word in set(re.findall(r"`([A-Z][A-Za-z0-9]+)`", line)):
                mentioned_classes.add(word)

        findings: list[Finding] = []

        # Find important classes that are missing from this page
        missing = all_classes - mentioned_classes

        # S-Fix-5: filter out abstract interfaces for cpp/python platforms
        if platform in CONCRETE_ONLY_PLATFORMS:
            missing = {
                cls for cls in missing
                if not _is_interface_entry(cls, class_kind.get(cls, ""))
            }

        important_missing = [
            (cls, class_importance.get(cls, 0.0))
            for cls in missing
            if class_importance.get(cls, 0.0) >= 0.4
        ]
        important_missing.sort(key=lambda x: x[1], reverse=True)

        if important_missing and len(important_missing) >= 3:
            top5 = important_missing[:5]
            names = ", ".join(f"`{c}`" for c, _ in top5)
            # H-05: reference pages get WARN for missing important classes
            _level = "WARN" if page.page_role == "reference" else "INFO"
            findings.append(Finding(
                level=_level,
                category="CG",
                filepath=str(page.filepath),
                line_no=1,
                message=f"{len(important_missing)} important classes not documented; top: {names}",
                suggestion="Consider documenting these high-value API classes",
                evaluator=self.name,
            ))

        # Also keep the global coverage check for very low coverage
        if mentioned_classes:
            coverage_pct = len(mentioned_classes & all_classes) / max(len(all_classes), 1) * 100
            if page.page_role == "docs" and coverage_pct < 5 and len(all_classes) > 10:
                findings.append(Finding(
                    level="INFO",
                    category="CG",
                    filepath=str(page.filepath),
                    line_no=1,
                    message=f"Low API coverage: {coverage_pct:.0f}% of {len(all_classes)} known classes mentioned",
                    suggestion="Consider documenting more classes from the API surface",
                    evaluator=self.name,
                ))

        # S-Fix-6: Enum reference-page coverage check
        findings.extend(self._check_enum_coverage(page))

        return findings

    # ------------------------------------------------------------------
    # S-Fix-6: Enum coverage second pass
    # ------------------------------------------------------------------

    def _check_enum_coverage(self, page: Page) -> list[Finding]:
        """Check whether enum types have corresponding reference pages.

        Loads api_surface.json, collects entries with kind==``enum_specifier``
        (C++) or ``enum_declaration`` (Java/.NET/Python), then checks whether
        a slugified file exists under
        ``content/reference.aspose.org/en/{family}/{platform}/``.

        Returns an INFO finding if ≥3 enums are missing reference pages.
        """
        if not page.family or not page.platform:
            return []

        # Only meaningful for reference-role pages
        if page.page_role != "reference":
            return []

        api_path = KNOWLEDGE_ROOT / page.family / page.platform / "merged" / "api_surface.json"
        if not api_path.exists():
            return []

        try:
            api_surface = json.loads(api_path.read_text(encoding="utf-8"))
        except (json.JSONDecodeError, OSError):
            return []

        _ENUM_KINDS = {
            "enum_specifier",       # C++
            "enum_declaration",     # Java / C#
            "enum_definition",      # alternative C++ / TS
        }

        enum_names = [
            entry["name"]
            for entry in api_surface
            if entry.get("kind") in _ENUM_KINDS and entry.get("name")
        ]

        if not enum_names:
            return []

        # Reference page root (English canonical path)
        ref_root = Path("content") / "reference.aspose.org" / "en" / page.family / page.platform

        missing_enums: list[str] = []
        for name in enum_names:
            slug = _to_slug(name)
            # Accept both <slug>.md and <slug>/_index.md
            if not (ref_root / f"{slug}.md").exists() and not (ref_root / slug / "_index.md").exists():
                missing_enums.append(name)

        if len(missing_enums) >= 3:
            top5 = missing_enums[:5]
            slugs_str = ", ".join(f"`{_to_slug(n)}`" for n in top5)
            return [Finding(
                level="INFO",
                category="CG",
                filepath=str(page.filepath),
                line_no=1,
                message=(
                    f"{len(missing_enums)} enum types lack reference pages; "
                    f"missing slugs (top {min(5, len(missing_enums))}): {slugs_str}"
                ),
                suggestion="Create reference pages for these enum types",
                evaluator=self.name,
            )]

        return []
