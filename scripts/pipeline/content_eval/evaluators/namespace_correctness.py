"""Namespace correctness evaluator — verifies import/using statements match FOSS packages.

H-15: Checks that code blocks use the correct FOSS package namespace, not
proprietary Aspose namespaces. The correct namespace is derived from
``knowledge/{family}/{platform}/model.yaml`` ``package_name`` field.

The evaluator loads the FOSS package_name and builds an allow-list of import
prefixes. Any import matching ``aspose.*`` / ``Aspose.*`` / ``com.aspose.*``
that is NOT in the allow-list is flagged as proprietary.

Emits FAIL for proprietary namespace in FOSS documentation code blocks.
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

# Platform → expected code block language tags
_PLATFORM_CODE_LANGS: dict[str, set[str]] = {
    "python": {"python", "py"},
    "net": {"csharp", "cs", "c#"},
    "java": {"java"},
    "cpp": {"cpp", "c++"},
    "typescript": {"typescript", "ts"},
    "javascript": {"javascript", "js"},
}

# Import extraction patterns per platform
# Each returns the full matched import text for reporting
_IMPORT_PATTERNS: dict[str, list[re.Pattern]] = {
    "python": [
        re.compile(r"\bfrom\s+(aspose\.\w+(?:\.\w+)*)\s+import\b"),
        re.compile(r"\bimport\s+(aspose\.\w+(?:\.\w+)*)"),
    ],
    "net": [
        re.compile(r"\busing\s+(Aspose\.\w+(?:\.\w+)*)\s*;"),
    ],
    "java": [
        re.compile(r"\bimport\s+(com\.aspose\.\w+(?:\.\w+)*)"),
    ],
    "cpp": [
        re.compile(r"\b(Aspose::\w+(?:::\w+)*)"),
    ],
}


def _build_allow_prefixes(foss_pkg: str, platform: str) -> set[str]:
    """Build a set of allowed import prefixes from the FOSS package name.

    For example:
        foss_pkg="aspose.slides_foss" → {"aspose.slides_foss"}
        foss_pkg="aspose.threed"      → {"aspose.threed"}
        foss_pkg="Aspose.Slides.Foss" → {"Aspose.Slides.Foss"}
        foss_pkg="com.aspose.threed"  → {"com.aspose.threed"}
    """
    if not foss_pkg:
        return set()
    prefixes = {foss_pkg}
    # For C++, also allow namespace::Foss variants
    if platform == "cpp" and "::" in foss_pkg:
        prefixes.add(foss_pkg.replace("::", "::"))
    return prefixes


def _is_allowed(import_path: str, allow_prefixes: set[str]) -> bool:
    """Check if an import path starts with any allowed FOSS prefix."""
    for prefix in allow_prefixes:
        if import_path == prefix or import_path.startswith(prefix + ".") or import_path.startswith(prefix + "::"):
            return True
    return False


class NamespaceCorrectnessEvaluator(BaseEvaluator):
    """Verify import/using statements use FOSS package namespaces."""

    name = "namespace_correctness"

    def evaluate(self, page: Page, knowledge: Any) -> list[Finding]:
        if not page.family or not page.platform:
            return []

        import_patterns = _IMPORT_PATTERNS.get(page.platform)
        if not import_patterns:
            return []

        expected_langs = _PLATFORM_CODE_LANGS.get(page.platform, set())

        # Load FOSS package name and build allow-list
        foss_pkg = self._load_package_name(page.family, page.platform)
        allow_prefixes = _build_allow_prefixes(foss_pkg, page.platform)

        # If no package_name configured, skip evaluation (can't determine
        # what's proprietary vs FOSS without a reference)
        if not allow_prefixes:
            return []

        findings: list[Finding] = []

        for block in page.code_blocks:
            lang = (block.lang or "").lower()
            if lang not in expected_langs:
                continue

            for pattern in import_patterns:
                for m in pattern.finditer(block.content):
                    import_path = m.group(1)

                    # Check if this import matches the FOSS package
                    if _is_allowed(import_path, allow_prefixes):
                        continue

                    line_no = block.start_line + block.content[:m.start()].count("\n")
                    matched_text = m.group(0)
                    suggestion = f"Use the FOSS package namespace `{foss_pkg}` instead of `{import_path}`"

                    findings.append(Finding(
                        level="FAIL",
                        category="NC",
                        filepath=str(page.filepath),
                        line_no=line_no,
                        message=(
                            f"Proprietary namespace `{import_path}` in FOSS "
                            f"documentation code (expected `{foss_pkg}`)"
                        ),
                        suggestion=suggestion,
                        evaluator=self.name,
                    ))

        return findings

    def _load_package_name(self, family: str, platform: str) -> str:
        """Load package_name from model.yaml for suggestion text."""
        model_path = KNOWLEDGE_ROOT / family / platform / "merged" / "model.yaml"
        if not model_path.exists():
            # Try scout path
            model_path = KNOWLEDGE_ROOT / family / platform / "scout" / "model.yaml"
        if not model_path.exists():
            return ""
        try:
            data = yaml.safe_load(model_path.read_text(encoding="utf-8"))
            return data.get("package_name", "") or data.get("package", "") or ""
        except Exception:
            return ""
