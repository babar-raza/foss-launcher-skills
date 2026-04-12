"""phantom_methods.py — Detect documented methods that do not exist in api_surface.json.

For reference pages only. Extracts method/property names from markdown
tables and verifies each against the knowledge model for the documented class.
Emits FAIL for any documented item not found in api_surface.json (PHANTOM).

This check addresses RC-01/RC-04: the generator can hallucinate plausible-sounding
methods that pass token-based validators (which check class presence, not method
existence). This check cross-references at the method level.

Pattern matched in markdown tables:
    | `method_name(...)` | description |
    | `method_name` | description |
    | `property_name` | type | ... |

Only runs on pages under content/reference.aspose.org/.
Class name is inferred from the markdown filename (e.g., ColorFormat.md -> ColorFormat).

Limitations:
- Cannot detect wrong types (only wrong existence)
- Inherited methods from base classes are allowed (walks parents via knowledge.has_method)
- Does not run on non-reference pages (docs, kb, blog, products)
"""
from __future__ import annotations

import re
import sys
from pathlib import Path
from typing import TYPE_CHECKING

_HERE = Path(__file__).resolve().parent.parent
if str(_HERE) not in sys.path:
    sys.path.insert(0, str(_HERE))

from token_ops import Finding  # noqa: E402

if TYPE_CHECKING:
    from knowledge_core import Knowledge  # pragma: no cover

# Pattern to extract METHOD names from markdown table cells.
# Only matches identifiers that appear with parentheses (| `method_name(...)` |)
# This avoids false positives from parameter tables (| `paramName` | Type |)
# and from property-only tables where bare identifiers appear.
# Handles: | `method_name()` | description |
#          | `method_name(params)` | description |
#          | `method()` → `ReturnType` | desc |
_TABLE_MEMBER_RE = re.compile(
    r"^\| *`([A-Za-z_][A-Za-z0-9_]*)\s*\("  # pipe, optional spaces, backtick, identifier, opening paren
)

# Reference page marker
_REFERENCE_PATH_MARKER = "reference.aspose.org"


def _is_reference_page(fp: Path) -> bool:
    """True if the file is under content/reference.aspose.org/."""
    normalised = str(fp).replace("\\", "/")
    return _REFERENCE_PATH_MARKER in normalised


def _infer_class_name(fp: Path) -> str:
    """Infer the primary class name from the file name (e.g., ColorFormat.md -> ColorFormat)."""
    return fp.stem  # stem drops the .md extension


# Names to skip — common type names, keywords, and non-API tokens that appear
# in backtick-quoted positions but are not method/property identifiers.
_SKIP_NAMES: frozenset[str] = frozenset({
    # Java/C#/Python primitive types and common class names
    "int", "long", "short", "byte", "float", "double", "boolean", "bool",
    "char", "void", "string", "String", "object", "Object",
    # Common identifiers that appear as parameter names/local variables
    "true", "false", "null", "None", "this", "self", "value", "name", "type",
    "key", "index", "item", "result", "obj", "args", "kwargs",
    # Markdown separator patterns
    "---", "===",
})


def _extract_documented_members(text: str) -> list[tuple[str, int]]:
    """Return (member_name, line_no) for API identifiers in table rows.

    Only captures the first backtick-quoted token after the leading pipe,
    which is the method/property name in standard reference page tables.
    Skips common type names and keywords.
    """
    members = []
    for lineno, line in enumerate(text.splitlines(), 1):
        if not line.startswith("|"):
            continue
        m = _TABLE_MEMBER_RE.match(line)
        if m:
            name = m.group(1)
            if name in _SKIP_NAMES:
                continue
            members.append((name, lineno))
    return members


def verify_phantom_methods(
    fp: Path,
    text: str,
    knowledge: "Knowledge",
) -> list[Finding]:
    """Return FAIL findings for documented members not in api_surface.json.

    Only active for reference pages. Skips if the class name is not in knowledge
    (prevents false positives for union/alias types without direct api_surface entries).
    """
    if not _is_reference_page(fp):
        return []

    # Skip low-coverage knowledge models (tier >= 2) where incomplete extraction
    # is expected — we cannot distinguish phantom from merely-not-extracted.
    tier = getattr(knowledge, "surface_tier", 1)
    if tier >= 2:
        return []

    cls_name = _infer_class_name(fp)

    # If the class is not in the knowledge model at all, we can't check its methods.
    # This prevents false positives on pages for types outside api_surface.json scope.
    if cls_name not in knowledge.classes:
        return []

    members = _extract_documented_members(text)
    if not members:
        return []

    findings = []
    seen = set()
    for member_name, lineno in members:
        if member_name in seen:
            continue
        seen.add(member_name)

        # Skip constructors: a method with the same name as the class is always valid
        # (e.g., A3DObject.A3DObject() is the constructor, not a phantom)
        if member_name == cls_name:
            continue

        # Check if the member exists on the class or any parent class
        exists = (
            knowledge.has_method(cls_name, member_name)
            or knowledge.has_property(cls_name, member_name)
            or knowledge.has_enum_member(cls_name, member_name)
        )

        if not exists:
            findings.append(Finding(
                level="FAIL",
                filepath=str(fp),
                line_no=lineno,
                message=(
                    f"PHANTOM_METHOD: `{cls_name}.{member_name}` is documented "
                    f"but not found in api_surface.json for this class or its parents"
                ),
                suggestion=(
                    f"Remove `{member_name}` from the documentation, or add it to "
                    f"api_surface.json if the extraction missed it. "
                    f"Verify against source: grep -r '{member_name}' runs/.clone_cache/"
                ),
            ))

    return findings
