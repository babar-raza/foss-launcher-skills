"""Type accuracy evaluator — detects known type mismatch patterns in C++ reference pages.

S-Fix-13
--------
The existing api_accuracy evaluator checks that API *names* exist (token-level).
It does NOT verify parameter types, return types, or static modifiers.
This evaluator catches those type inaccuracies in generated pages.

Checks performed (cpp platform only)
--------------------------------------
1. **string& instead of string_view** — ``const std::string&`` in parameter
   positions where Aspose FOSS C++ style uses ``std::string_view``.
   Emits WARN.

2. **float for geometry properties** — ``float`` as the type of properties
   named x, y, width, height, or rotation; these should be ``double`` in
   Aspose FOSS.  Emits WARN.

3. **Static modifier mismatch** — if a method is documented with a ``static``
   keyword in a code example, the evaluator extracts the class/method name
   and (if api_surface.json is available) checks whether the method is marked
   static there.  If it is not found as static, emits INFO.

These are WARNING/INFO findings — not FAIL.  The evaluator is intentionally
conservative (opt-in, cpp only, narrow patterns) to avoid false positives.
"""

from __future__ import annotations

import json
import re
from pathlib import Path
from typing import Any

from ..models import Finding, Page
from . import BaseEvaluator

# ---------------------------------------------------------------------------
# Pattern constants
# ---------------------------------------------------------------------------

# Pattern 1: const std::string& in a parameter position.
# Matches e.g. "const std::string& path", "const std::string &name"
_STRING_REF_RE = re.compile(
    r"\bconst\s+std\s*::\s*string\s*&",
    re.MULTILINE,
)

# Pattern 2: float followed by a geometry property name.
# Matches e.g. "float x", "float width", "float height", "float rotation", "float y"
_FLOAT_GEOM_RE = re.compile(
    r"\bfloat\s+(?P<prop>x|y|width|height|rotation)\b",
    re.IGNORECASE | re.MULTILINE,
)

# Pattern 3: static method declaration in a code block.
# Extracts: optional class qualifier and method name from lines like
#   "static ReturnType ClassName::MethodName(" or
#   "static ReturnType MethodName("
_STATIC_DECL_RE = re.compile(
    r"\bstatic\b[^;{(]*\b(?:(?P<cls>[A-Z][A-Za-z0-9_]*)::)?(?P<method>[A-Za-z_][A-Za-z0-9_]*)\s*\(",
    re.MULTILINE,
)

# Code-block language tags that map to C++
_CPP_LANGS = {"cpp", "c++", "cxx"}

KNOWLEDGE_ROOT = Path("knowledge")


class TypeAccuracyEvaluator(BaseEvaluator):
    """Detects known type mismatch patterns in C++ reference/docs pages.

    Platform guard: only runs on pages where ``page.platform == "cpp"``.
    Findings are WARN or INFO — never FAIL — to stay conservative.
    """

    name = "type_accuracy"

    def evaluate(self, page: Page, knowledge: Any) -> list[Finding]:
        # Guard: only meaningful for cpp platform pages
        if page.platform != "cpp":
            return []

        findings: list[Finding] = []

        # Collect cpp-tagged code blocks only
        cpp_blocks = [b for b in page.code_blocks if b.lang in _CPP_LANGS]
        if not cpp_blocks:
            return []

        # Load api_surface for static-check (best-effort; skip if missing)
        api_surface = self._load_api_surface(page)

        for block in cpp_blocks:
            findings.extend(self._check_string_ref(block.content, block.start_line, page))
            findings.extend(self._check_float_geometry(block.content, block.start_line, page))
            findings.extend(self._check_static_modifier(block.content, block.start_line, page, api_surface))

        return findings

    # ------------------------------------------------------------------
    # Check 1: const std::string& instead of std::string_view
    # ------------------------------------------------------------------

    def _check_string_ref(self, code: str, start_line: int, page: Page) -> list[Finding]:
        findings: list[Finding] = []
        for m in _STRING_REF_RE.finditer(code):
            line_no = start_line + code[: m.start()].count("\n")
            findings.append(Finding(
                level="WARN",
                category="TA",
                filepath=str(page.filepath),
                line_no=line_no,
                message=(
                    "Parameter type uses const string& — verify against header "
                    "(may need std::string_view)"
                ),
                suggestion="Replace `const std::string&` with `std::string_view` if the header uses it",
                evaluator=self.name,
            ))
        return findings

    # ------------------------------------------------------------------
    # Check 2: float for geometry properties (should be double)
    # ------------------------------------------------------------------

    def _check_float_geometry(self, code: str, start_line: int, page: Page) -> list[Finding]:
        findings: list[Finding] = []
        for m in _FLOAT_GEOM_RE.finditer(code):
            prop = m.group("prop").lower()
            line_no = start_line + code[: m.start()].count("\n")
            findings.append(Finding(
                level="WARN",
                category="TA",
                filepath=str(page.filepath),
                line_no=line_no,
                message=(
                    f"Geometry property `{prop}` typed as `float` — "
                    "Aspose FOSS C++ uses `double` for geometry values"
                ),
                suggestion=f"Change `float {prop}` to `double {prop}`",
                evaluator=self.name,
            ))
        return findings

    # ------------------------------------------------------------------
    # Check 3: static modifier — cross-check with api_surface.json
    # ------------------------------------------------------------------

    def _check_static_modifier(
        self,
        code: str,
        start_line: int,
        page: Page,
        api_surface: list[dict],
    ) -> list[Finding]:
        findings: list[Finding] = []
        for m in _STATIC_DECL_RE.finditer(code):
            method_name = m.group("method")
            cls_name = m.group("cls")  # may be None

            # Skip common C++ keywords that match the pattern
            if method_name in (
                "if", "while", "for", "switch", "return", "class",
                "struct", "namespace", "void", "int", "bool",
            ):
                continue

            # If no api_surface available → always emit INFO
            if not api_surface:
                line_no = start_line + code[: m.start()].count("\n")
                findings.append(Finding(
                    level="INFO",
                    category="TA",
                    filepath=str(page.filepath),
                    line_no=line_no,
                    message=(
                        f"Method `{method_name}` documented as `static` — "
                        "verify against API surface (api_surface.json not found)"
                    ),
                    suggestion="Confirm static modifier in the source header",
                    evaluator=self.name,
                ))
                continue

            # Check api_surface for this method
            is_static_in_surface = self._is_static_in_surface(
                method_name, cls_name, api_surface
            )

            if is_static_in_surface is False:
                # Method found but NOT static — flag it
                line_no = start_line + code[: m.start()].count("\n")
                label = f"{cls_name}::{method_name}" if cls_name else method_name
                findings.append(Finding(
                    level="INFO",
                    category="TA",
                    filepath=str(page.filepath),
                    line_no=line_no,
                    message=(
                        f"Method `{label}` documented as `static` but not "
                        "marked static in api_surface.json"
                    ),
                    suggestion="Remove `static` modifier or verify the header",
                    evaluator=self.name,
                ))
            # If is_static_in_surface is True → correct, no finding
            # If is_static_in_surface is None → not found, skip (api may be incomplete)

        return findings

    # ------------------------------------------------------------------
    # Helpers
    # ------------------------------------------------------------------

    def _load_api_surface(self, page: Page) -> list[dict]:
        """Load api_surface.json for this page's family/platform.

        Returns an empty list if the file is absent or unparseable.
        """
        if not page.family or not page.platform:
            return []
        api_path = (
            KNOWLEDGE_ROOT / page.family / page.platform / "merged" / "api_surface.json"
        )
        if not api_path.exists():
            return []
        try:
            return json.loads(api_path.read_text(encoding="utf-8"))
        except (json.JSONDecodeError, OSError):
            return []

    def _is_static_in_surface(
        self,
        method_name: str,
        cls_name: str | None,
        api_surface: list[dict],
    ) -> bool | None:
        """Return True if found+static, False if found+not-static, None if not found."""
        for entry in api_surface:
            name = entry.get("name", "")
            if name != method_name:
                continue
            # If we have a class qualifier, filter by it
            if cls_name and entry.get("parent") and entry["parent"] != cls_name:
                continue
            # Found the method — check static flag
            return bool(entry.get("is_static", False))
        return None
