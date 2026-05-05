"""Type accuracy evaluator — detects type mismatch patterns in reference pages.

S-Fix-13
--------
The existing api_accuracy evaluator checks that API *names* exist (token-level).
It does NOT verify parameter types, return types, or static modifiers.
This evaluator catches those type inaccuracies in generated pages.

Checks performed
--------------------------------------
1. **string& instead of string_view** — ``const std::string&`` in parameter
   positions where Aspose FOSS C++ style uses ``std::string_view``.
   Emits WARN. (cpp only)

2. **float for geometry properties** — ``float`` as the type of properties
   named x, y, width, height, or rotation; these should be ``double`` in
   Aspose FOSS.  Emits WARN. (cpp only)

3. **Static modifier mismatch** — if a method is documented with a ``static``
   keyword in a code example, the evaluator extracts the class/method name
   and (if api_surface.json is available) checks whether the method is marked
   static there.  If it is not found as static, emits INFO. (cpp only)

4. **Property access mode mismatch** — if a reference page Property table shows
   "Read" access for a property that api_surface.json marks as ``writable: true``,
   emits FAIL. (all platforms, reference subdomain only)
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

# Pattern 4: Property table row — | `PropName` | SomeType | Read | Description |
# Captures prop name and access value (Read / Read/Write / Write)
_PROP_TABLE_ROW_RE = re.compile(
    r"^\|\s*`(?P<prop>[^`]+)`\s*\|[^|]*\|\s*(?P<access>Read|Write|Read/Write)\s*\|",
    re.MULTILINE,
)

# Pattern 5: Method table row — | `MethodName(args)` | `ReturnType` | Description |
# Captures method name (without args) and return type cell content
_METHOD_TABLE_ROW_RE = re.compile(
    r"^\|\s*`(?P<method>[A-Za-z_][A-Za-z0-9_]*)\s*\([^)]*\)`\s*\|\s*`?(?P<ret>[^`|]*)`?\s*\|",
    re.MULTILINE,
)

# Return type values that count as "blank/void" (no meaningful type documented).
# Note: "none" is intentionally excluded — Python None IS a meaningful return type.
_VOID_RETURN_VALUES = {"", "void", "null", "n/a", "-"}

try:
    from config_loader import resolve_knowledge_root as _resolve_knowledge_root
    KNOWLEDGE_ROOT = _resolve_knowledge_root()
except Exception:
    KNOWLEDGE_ROOT = Path("knowledge")


class TypeAccuracyEvaluator(BaseEvaluator):
    """Detects known type mismatch patterns in C++ reference/docs pages.

    Platform guard: only runs on pages where ``page.platform == "cpp"``.
    Findings are WARN or INFO — never FAIL — to stay conservative.
    """

    name = "type_accuracy"

    def evaluate(self, page: Page, knowledge: Any) -> list[Finding]:
        findings: list[Finding] = []
        api_surface = self._load_api_surface(page)

        # Check 4: property access mode (all platforms, reference pages only)
        if page.subdomain == "reference" and api_surface:
            findings.extend(self._check_property_access(page, api_surface))

        # Check 5: method return type vs api_surface (all platforms, reference pages only)
        if page.subdomain == "reference" and api_surface:
            findings.extend(self._check_return_types(page, api_surface))

        # FR-17b: reference_void_mismatch — FAIL when table explicitly shows void/None
        # but api_surface has a non-void return type
        if page.subdomain == "reference" and api_surface:
            findings.extend(self._check_reference_void_mismatch(page, api_surface))

        # Checks 1-3: C++ only
        if page.platform == "cpp":
            cpp_blocks = [b for b in page.code_blocks if b.lang in _CPP_LANGS]
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
    # Check 4: property access mode vs api_surface writable flag
    # ------------------------------------------------------------------

    def _check_property_access(
        self,
        page: Page,
        api_surface: list[dict],
    ) -> list[Finding]:
        """Emit FAIL when a reference page says 'Read' but api_surface has writable=True.

        Class-scoped: only checks properties belonging to the class named by the
        page filename (e.g. ``Presentation.md`` → checks ``Presentation`` class only).
        """
        findings: list[Finding] = []

        # Derive class name from page filename
        class_name = page.filepath.stem

        # Build name → writable lookup from the matching class only
        writable_map: dict[str, bool] = {}
        for entry in api_surface:
            if entry.get("name") != class_name:
                continue
            for prop in entry.get("properties", []):
                pname = prop.get("name", "")
                if pname:
                    writable_map[pname] = bool(prop.get("writable", False))
            break  # only one class matches

        if not writable_map:
            return findings

        raw = page.filepath.read_text(encoding="utf-8", errors="replace")
        for m in _PROP_TABLE_ROW_RE.finditer(raw):
            prop_name = m.group("prop")
            access_val = m.group("access")
            if access_val != "Read":
                continue
            if writable_map.get(prop_name) is True:
                line_no = raw[: m.start()].count("\n") + 1
                findings.append(Finding(
                    level="FAIL",
                    category="TA",
                    filepath=str(page.filepath),
                    line_no=line_no,
                    message=(
                        f"Property `{prop_name}` documented as Read-only but "
                        "api_surface marks it as writable (has a setter)"
                    ),
                    suggestion=(
                        f"Change Access column for `{prop_name}` from `Read` to `Read/Write`"
                    ),
                    evaluator=self.name,
                ))

        return findings

    # ------------------------------------------------------------------
    # Check 5: method return type vs api_surface
    # ------------------------------------------------------------------

    def _check_return_types(
        self,
        page: Page,
        api_surface: list[dict],
    ) -> list[Finding]:
        """Emit WARN when a method table shows blank/void return but api_surface has one.

        Class-scoped: only checks methods belonging to the class named by filename.
        Scope: reference pages only.
        """
        findings: list[Finding] = []

        class_name = page.frontmatter.get("linkTitle", "") or page.filepath.stem
        if not class_name:
            return findings

        # Build method name → return_type from api_surface for this class
        return_type_map: dict[str, str] = {}
        for entry in api_surface:
            if entry.get("name") != class_name:
                continue
            for method in entry.get("methods", []):
                mname = method.get("name", "")
                mtype = (method.get("return_type") or "").strip()
                if mname and mtype and mtype.lower() not in _VOID_RETURN_VALUES:
                    return_type_map[mname] = mtype
            break

        if not return_type_map:
            return findings

        raw = page.filepath.read_text(encoding="utf-8", errors="replace")
        for m in _METHOD_TABLE_ROW_RE.finditer(raw):
            method_name = m.group("method")
            ret_cell = m.group("ret").strip().lower()

            if method_name not in return_type_map:
                continue
            if ret_cell in _VOID_RETURN_VALUES:
                line_no = raw[: m.start()].count("\n") + 1
                expected = return_type_map[method_name]
                findings.append(Finding(
                    level="WARN",
                    category="TA",
                    filepath=str(page.filepath),
                    line_no=line_no,
                    message=(
                        f"Method `{method_name}()` return type is blank/void in table but "
                        f"api_surface shows `{expected}`"
                    ),
                    suggestion=f"Set Return Type column for `{method_name}()` to `{expected}`",
                    evaluator=self.name,
                ))

        return findings

    # ------------------------------------------------------------------
    # FR-17b: reference_void_mismatch — FAIL when table explicitly says void/None
    # ------------------------------------------------------------------

    # Explicit void/None values in the return-type cell (not just blank)
    _EXPLICIT_VOID_CELL_RE = re.compile(
        r"^\|\s*`(?P<method>[A-Za-z_][A-Za-z0-9_]*)\s*\([^)]*\)`\s*\|\s*`?(?P<ret>void|None|null)`?\s*\|",
        re.MULTILINE | re.IGNORECASE,
    )

    def _check_reference_void_mismatch(
        self,
        page: Page,
        api_surface: list[dict],
    ) -> list[Finding]:
        """Emit FAIL when a method table explicitly documents void/None but api_surface
        shows a definitive non-void return type.

        This differs from Check 5 (_check_return_types) which catches *blank* return
        cells.  This check catches *explicit* void/None that contradicts the source.
        """
        findings: list[Finding] = []

        class_name = page.frontmatter.get("linkTitle", "") or page.filepath.stem
        if not class_name:
            return findings

        # Build method → return_type map for non-void methods.
        # Include "none" here because documenting None for a None-returning
        # method is correct — the global _VOID_RETURN_VALUES excludes "none"
        # since Python None is a meaningful return type for Check 5, but for
        # this void-mismatch check None==None is not a mismatch.
        _void_for_mismatch = _VOID_RETURN_VALUES | {"none"}
        return_type_map: dict[str, str] = {}
        for entry in api_surface:
            if entry.get("name") != class_name:
                continue
            for method in entry.get("methods", []):
                mname = method.get("name", "")
                mtype = (method.get("return_type") or "").strip()
                if mname and mtype and mtype.lower() not in _void_for_mismatch:
                    return_type_map[mname] = mtype
            break

        if not return_type_map:
            return findings

        raw = page.filepath.read_text(encoding="utf-8", errors="replace")

        # Detect overloaded methods: if the same method name appears in
        # multiple table rows with DIFFERENT return types, some overloads
        # legitimately return void while others don't. Skip these.
        _all_rows = _METHOD_TABLE_ROW_RE.findall(raw) if hasattr(_METHOD_TABLE_ROW_RE, 'findall') else []
        from collections import Counter as _Counter
        _method_row_counts = _Counter(name for name, _ in _all_rows)
        _overloaded = {name for name, count in _method_row_counts.items() if count > 1}

        for m in self._EXPLICIT_VOID_CELL_RE.finditer(raw):
            method_name = m.group("method")
            if method_name not in return_type_map:
                continue
            # Skip overloaded methods — void overload is likely correct
            if method_name in _overloaded:
                continue
            line_no = raw[: m.start()].count("\n") + 1
            expected = return_type_map[method_name]
            findings.append(Finding(
                level="FAIL",
                category="TA",
                filepath=str(page.filepath),
                line_no=line_no,
                message=(
                    f"Method `{method_name}()` explicitly documented as returning "
                    f"`void`/`None` but api_surface shows return type `{expected}`"
                ),
                suggestion=(
                    f"Change the Return Type cell for `{method_name}()` from void/None "
                    f"to `{expected}`"
                ),
                evaluator=self.name,
            ))

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
