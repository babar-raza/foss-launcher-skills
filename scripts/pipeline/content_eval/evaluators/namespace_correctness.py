"""Namespace correctness evaluator — verifies import/using statements match FOSS packages.

H-15: Checks that code blocks use the correct FOSS package namespace, not
proprietary Aspose namespaces.

For C#/.NET the allow-list is built from ``canonical_namespace`` values in
``api_surface.json`` — the actual source-code namespaces — NOT from the NuGet
package name (which is the *PackageId*, not a compilable namespace).  For other
platforms the allow-list is derived from ``model.yaml`` ``package_name``.

Emits FAIL for proprietary namespace in FOSS documentation code blocks.
"""

from __future__ import annotations

import json
import re
from pathlib import Path
from typing import Any

import yaml

from ..models import Finding, Page
from . import BaseEvaluator

_DEFAULT_KNOWLEDGE_ROOT = Path(__file__).resolve().parents[4] / "knowledge"
KNOWLEDGE_ROOT = _DEFAULT_KNOWLEDGE_ROOT


def configure(*, knowledge_root: "Path | str | None" = None) -> None:
    """Override module-level path constants for testing."""
    global KNOWLEDGE_ROOT
    KNOWLEDGE_ROOT = Path(knowledge_root) if knowledge_root is not None else _DEFAULT_KNOWLEDGE_ROOT

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
        # Dot-prefix (proprietary Aspose SDK style): from aspose.font import ...
        re.compile(r"\bfrom\s+(aspose\.\w+(?:\.\w+)*)\s+import\b"),
        re.compile(r"\bimport\s+(aspose\.\w+(?:\.\w+)*)"),
        # Underscore-prefix (FOSS PyPI style): from aspose_font import ...
        re.compile(r"\bfrom\s+(aspose_\w+(?:\.\w+)*)\s+import\b"),
        re.compile(r"\bimport\s+(aspose_\w+(?:\.\w+)*)"),
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
    "typescript": [
        # ES6 named/default/namespace import: import ... from '@aspose/...' or 'aspose-...'
        re.compile(r"""\bimport\b[^'";\n]*from\s+['"](@aspose/[\w/-]+|aspose-[\w-]+(?:/[\w-]+)*)['"]"""),
        # CommonJS require: require('@aspose/...')
        re.compile(r"""\brequire\s*\(\s*['"](@aspose/[\w/-]+|aspose-[\w-]+(?:/[\w-]+)*)['"]"""),
    ],
    "javascript": [
        re.compile(r"""\bimport\b[^'";\n]*from\s+['"](@aspose/[\w/-]+|aspose-[\w-]+(?:/[\w-]+)*)['"]"""),
        re.compile(r"""\brequire\s*\(\s*['"](@aspose/[\w/-]+|aspose-[\w-]+(?:/[\w-]+)*)['"]"""),
    ],
}


def _load_canonical_namespaces(family: str, platform: str) -> set[str]:
    """Load unique canonical_namespace values from api_surface.json.

    For C#/.NET the NuGet PackageId (e.g. ``Aspose.Pdf.Foss``) is NOT a valid
    namespace.  The real namespaces live in ``canonical_namespace`` fields
    extracted from source code (e.g. ``Aspose.Pdf``, ``Aspose.Pdf.Text``).
    """
    api_path = KNOWLEDGE_ROOT / family / platform / "merged" / "api_surface.json"
    if not api_path.exists():
        return set()
    try:
        entries = json.loads(api_path.read_text(encoding="utf-8"))
        return {
            e["canonical_namespace"]
            for e in entries
            if e.get("canonical_namespace")
        }
    except Exception:
        return set()


def _build_allow_prefixes(foss_pkg: str, platform: str,
                          canonical_namespaces: set[str] | None = None) -> set[str]:
    """Build a set of allowed import prefixes.

    For C#/.NET (``platform="net"``), uses ``canonical_namespaces`` from
    api_surface.json — the actual source-code namespaces.  The NuGet PackageId
    is deliberately excluded because it is not a compilable namespace.

    For other platforms the FOSS package name is the import root.
    """
    # C#/.NET: use real source-code namespaces, not the NuGet PackageId
    if platform == "net" and canonical_namespaces:
        return canonical_namespaces

    if not foss_pkg:
        return set()
    prefixes = {foss_pkg}
    # Python: PyPI package names use hyphens (aspose-font) but import roots use
    # underscores (aspose_font). Add the underscore form to the allow-list.
    if platform == "python":
        prefixes.add(foss_pkg.replace("-", "_"))
    # For C++, also allow namespace::Foss variants
    if platform == "cpp" and "::" in foss_pkg:
        prefixes.add(foss_pkg.replace("::", "::"))
    return prefixes


def _is_allowed(import_path: str, allow_prefixes: set[str],
                exact_only: bool = False) -> bool:
    """Check if an import path is allowed.

    When *exact_only* is True (C# with canonical namespaces), only exact
    matches are accepted — prefix matching is disabled because the canonical
    set already enumerates every valid namespace at every depth.
    """
    if exact_only:
        return import_path in allow_prefixes
    for prefix in allow_prefixes:
        if (import_path == prefix
                or import_path.startswith(prefix + ".")
                or import_path.startswith(prefix + "::")
                or import_path.startswith(prefix + "/")):  # npm scoped: @aspose/3d/sub
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
        canonical_ns = _load_canonical_namespaces(page.family, page.platform)
        allow_prefixes = _build_allow_prefixes(foss_pkg, page.platform,
                                               canonical_ns)
        # C# with canonical namespaces: exact match only (the canonical set
        # already contains every valid namespace — prefix matching would let
        # the NuGet PackageId slip through as a child of the root namespace)
        use_exact = bool(page.platform == "net" and canonical_ns)

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

                    # Check if this import matches a known FOSS namespace
                    if _is_allowed(import_path, allow_prefixes, use_exact):
                        continue

                    line_no = block.start_line + block.content[:m.start()].count("\n")
                    if canonical_ns:
                        suggestion = (
                            f"Use a valid source-code namespace instead of "
                            f"`{import_path}`. Known namespaces: "
                            + ", ".join(f"`{ns}`" for ns in sorted(canonical_ns)[:5])
                            + (" ..." if len(canonical_ns) > 5 else "")
                        )
                    else:
                        suggestion = f"Use the FOSS package namespace `{foss_pkg}` instead of `{import_path}`"

                    findings.append(Finding(
                        level="FAIL",
                        category="NC",
                        filepath=str(page.filepath),
                        line_no=line_no,
                        message=(
                            f"Invalid namespace `{import_path}` in FOSS "
                            f"documentation code block"
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
