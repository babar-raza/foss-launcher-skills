"""tree_helpers.py — Tree-sitter parser loading and generic tree utilities.

Extracted from scout.py (step 4.1). Contains:
- Language constants (_CLASS_TYPES, _FUNC_TYPES, etc.)
- Parser loading (get_parser, _LANG_ALIASES)
- Generic tree helpers (collect_nodes, node_text, child_by_field, etc.)
- Visibility check (is_public)
- Source file collection (_collect_source_files)
- Base class / enum member extraction helpers

No Scout class dependencies — these are pure functions usable in isolation.
"""
from __future__ import annotations

import re
from pathlib import Path
from typing import Any

MAX_FILES = 500  # shared cap for _collect_source_files


# ---------------------------------------------------------------------------
# Language mapping constants
# ---------------------------------------------------------------------------

PLATFORM_TO_LANG: dict[str, str] = {
    "python": "python",
    "net": "csharp",
    "dotnet": "csharp",  # kept for backward compatibility
    "java": "java",
    "cpp": "cpp",
    "typescript": "typescript",
    "javascript": "javascript",
    "nodejs": "javascript",
    "go": "go",
}

_CLASS_TYPES: dict[str, set[str]] = {
    "java": {"class_declaration", "interface_declaration", "enum_declaration",
             "annotation_type_declaration"},
    "csharp": {"class_declaration", "interface_declaration", "enum_declaration",
               "struct_declaration", "record_declaration"},
    "javascript": {"class_declaration"},
    "typescript": {"class_declaration", "interface_declaration",
                   "type_alias_declaration", "enum_declaration"},
    "cpp": {"class_specifier", "struct_specifier", "enum_specifier"},
    "python": {"class_definition"},
    "go": {"type_declaration", "type_spec"},
}

_FUNC_TYPES: dict[str, set[str]] = {
    "java": {"method_declaration", "constructor_declaration"},
    "csharp": {"method_declaration", "constructor_declaration",
               "property_declaration"},
    "javascript": {"function_declaration", "method_definition", "arrow_function",
                   "public_field_definition"},
    "typescript": {"function_declaration", "method_definition", "arrow_function",
                   "public_field_definition", "property_signature", "method_signature"},
    "go": {"function_declaration", "method_declaration"},
    "cpp": {"function_definition"},
    "python": {"function_definition"},
}

_PY_ENUM_BASES: frozenset[str] = frozenset({
    "Enum", "IntEnum", "StrEnum", "Flag", "IntFlag",
    "enum.Enum", "enum.IntEnum", "enum.StrEnum", "enum.Flag", "enum.IntFlag",
})

_IMPORT_TYPES: dict[str, set[str]] = {
    "java": {"import_declaration"},
    "csharp": {"using_directive"},
    "javascript": {"import_statement"},
    "typescript": {"import_statement"},
    "go": {"import_declaration"},
    "cpp": set(),
    "python": {"import_statement", "import_from_statement"},
}

_MODULE_TYPES: dict[str, set[str]] = {
    "java": {"package_declaration"},
    "csharp": {"namespace_declaration"},
    "javascript": set(),
    "typescript": set(),
    "go": {"package_clause"},
    "cpp": {"namespace_definition"},
    "python": set(),
}

_NOT_IMPL_PATTERNS: dict[str, re.Pattern[str]] = {
    "python": re.compile(r"raise\s+NotImplementedError"),
    "csharp": re.compile(r"throw\s+new\s+NotImplementedException\s*\("),
    "java": re.compile(r"throw\s+new\s+UnsupportedOperationException\s*\("),
    "cpp": re.compile(r'throw\s+std::runtime_error\s*\(\s*"not implemented"',
                      re.IGNORECASE),
    "javascript": re.compile(r'throw\s+new\s+Error\s*\(\s*"not implemented"',
                              re.IGNORECASE),
    "typescript": re.compile(r'throw\s+new\s+Error\s*\(\s*"not implemented"',
                              re.IGNORECASE),
    # SFX-5: Go uses errors.New/fmt.Errorf with "not implemented" strings, or panic.
    "go": re.compile(
        r'errors\.New\s*\(\s*"not implemented"\s*\)'
        r'|fmt\.Errorf\s*\(\s*"not implemented[^"]*"\s*\)'
        r'|panic\s*\(\s*"not implemented[^"]*"\s*\)',
        re.IGNORECASE,
    ),
}

_FILE_EXTENSIONS: dict[str, str] = {
    "python": ".py",
    "csharp": ".cs",
    "java": ".java",
    "cpp": ".cpp",
    "typescript": ".ts",
    "javascript": ".js",
    "go": ".go",
}

_HEADER_EXTENSIONS: dict[str, str | list[str]] = {
    "cpp": [".h", ".hpp"],
}

_DOC_COMMENT_STYLES: dict[str, str] = {
    "java": "javadoc",
    "csharp": "xml_doc",
    "javascript": "jsdoc",
    "typescript": "jsdoc",
    "cpp": "javadoc",
    "python": "docstring",
    "go": "godoc",
}


# ---------------------------------------------------------------------------
# Parser loading
# ---------------------------------------------------------------------------

_LANG_ALIASES: dict[str, str] = {"csharp": "_c_sharp_separate"}


def get_parser(language: str):
    """Return a tree-sitter Parser for *language*."""
    resolved = _LANG_ALIASES.get(language, language)
    if resolved == "_c_sharp_separate":
        import tree_sitter_c_sharp as tsc
        from tree_sitter import Language, Parser
        lang_obj = Language(tsc.language())
        parser = Parser(lang_obj)
        return parser
    else:
        from tree_sitter_language_pack import get_parser as _get
        return _get(resolved)


# ---------------------------------------------------------------------------
# Generic tree helpers
# ---------------------------------------------------------------------------

def collect_nodes(root, type_names: set[str]) -> list:
    """Iterative depth-first collection of nodes whose type is in *type_names*."""
    result: list = []
    stack = [root]
    while stack:
        node = stack.pop()
        if node.type in type_names:
            result.append(node)
        stack.extend(reversed(node.children))
    return result


def node_text(node) -> str:
    """Return the UTF-8 text of a tree-sitter node."""
    if node is None:
        return ""
    return node.text.decode("utf-8", errors="replace")


def child_by_field(node, name: str):
    """Return child_by_field_name, tolerating None."""
    try:
        return node.child_by_field_name(name)
    except Exception:
        return None


def find_child_by_type(node, type_name: str):
    """Return the first direct child with the given type."""
    for ch in node.children:
        if ch.type == type_name:
            return ch
    return None


def find_children_by_type(node, type_name: str) -> list:
    """Return all direct children with the given type."""
    return [ch for ch in node.children if ch.type == type_name]


def _node_name(node, language: str) -> str:
    """Extract the identifier name from a declaration node."""
    name_node = child_by_field(node, "name")
    if name_node:
        return node_text(name_node)
    # fallback: first identifier child
    for ch in node.children:
        if ch.type == "identifier" or ch.type == "type_identifier":
            return node_text(ch)
    return ""


# ---------------------------------------------------------------------------
# Visibility check
# ---------------------------------------------------------------------------

def is_public(node, language: str) -> bool:
    """Return True if *node* represents a public declaration."""
    name = _node_name(node, language)
    if not name:
        return False

    if language == "go":
        return name[0].isupper()

    if language == "python":
        if name == "__init__":
            return True
        return not name.startswith("_")

    if language in ("javascript", "typescript"):
        parent = node.parent
        # Class/interface members are public unless explicitly private/protected
        if parent and parent.type in ("class_body", "interface_body", "object_type"):
            for ch in node.children:
                if ch.type == "accessibility_modifier":
                    if node_text(ch) in ("private", "protected"):
                        return False
            if name.startswith("#"):
                return False
            # FIX-03: TypeScript convention uses _ prefix for private members.
            # Many TS libraries use this convention without explicit modifiers.
            if name.startswith("_"):
                return False
            return True
        if parent and parent.type == "export_statement":
            return True
        # top-level declarations in modules are considered public
        if parent and parent.type in ("program", "module"):
            return True
        return False

    if language in ("java", "csharp", "cpp"):
        # C++ top-level classes/structs are implicitly public API
        if language == "cpp" and node.type in ("class_specifier", "struct_specifier",
                                                "enum_specifier"):
            parent = node.parent
            if parent and parent.type in ("translation_unit", "declaration",
                                           "namespace_definition",
                                           "declaration_list"):
                return True
            if parent and parent.type == "declaration":
                gp = parent.parent
                if gp and gp.type in ("translation_unit", "namespace_definition",
                                       "declaration_list"):
                    return True
        for ch in node.children:
            if ch.type == "modifiers" or ch.type == "modifier":
                if "public" in node_text(ch):
                    return True
                return False
            if ch.type == "public":
                return True
        # C# / Java: interface members are implicitly public
        if node.parent and node.parent.type in ("interface_declaration",
                                                  "interface_body",
                                                  "declaration_list"):
            gp = node.parent
            if gp.type in ("declaration_list", "interface_body"):
                gp = gp.parent
            if gp and gp.type == "interface_declaration":
                return True
        # C++: check access specifier in class body
        if language == "cpp":
            prev = node.prev_named_sibling
            while prev:
                if prev.type == "access_specifier":
                    return "public" in node_text(prev)
                prev = prev.prev_named_sibling
        return False

    return True


def visibility_tier(node, language: str, *, has_docstring: bool = False,
                     in_module_all: bool = False) -> str:
    """Return visibility tier for a node that already passed is_public().

    Tiers (highest to lowest signal):
      "exported"     — Explicitly exported (__all__, export keyword, Go uppercase)
      "public"       — Explicitly public (modifier) or documented (has docstring)
      "conventional" — Public by naming convention only (no explicit marker)

    For Python, callers should pass *has_docstring* and *in_module_all* since
    those require context beyond the tree-sitter node itself.
    """
    if language == "python":
        if in_module_all:
            return "exported"
        if has_docstring:
            return "public"
        return "conventional"
    if language in ("java", "csharp", "cpp"):
        return "public"
    if language in ("javascript", "typescript"):
        parent = node.parent
        if parent and parent.type == "export_statement":
            return "exported"
        return "public"
    if language == "go":
        return "exported"
    return "public"


# ---------------------------------------------------------------------------
# Source file collection
# ---------------------------------------------------------------------------

# Directories that should never contribute to the public API surface.
_NON_PUBLIC_DIRS: frozenset[str] = frozenset({
    "tests", "test", "spec", "specs",
    "examples", "example", "samples", "sample", "demo", "demos",
    "docs", "doc", "documentation",
    ".github", ".git",
    "benchmarks", "benchmark", "perf",
    "scripts", "tools", "build", "dist",
})


def _is_non_public_path(p: Path, root: Path) -> bool:
    """Return True if any path component relative to *root* is a non-public directory."""
    try:
        parts = p.relative_to(root).parts
    except ValueError:
        parts = p.parts
    return any(part.lower() in _NON_PUBLIC_DIRS for part in parts)


_FORMAT_STEM_RE = re.compile(
    r"(format|exporter|importer|loader|saver|reader|writer)", re.IGNORECASE
)


def _collect_source_files(root: Path, ext: str, header_ext: str | list[str] = "") -> list[Path]:
    """Glob for source files, capped at MAX_FILES, excluding non-public directories.

    Files are ordered by a three-tier priority key so critical extraction
    targets are never evicted by the MAX_FILES cap:
      0 — _internal/ implementation files (exporter/parser classes live here)
      1 — format-enum and I/O-class files (SaveFormat, SourceFormat, *Exporter …)
      2 — all other public source files (alphabetical within tier)
    """
    def _priority(p: Path) -> tuple:
        rel = p.relative_to(root).as_posix()
        if "/_internal/" in rel:
            return (0, rel)
        if _FORMAT_STEM_RE.search(p.stem):
            return (1, rel)
        return (2, rel)

    files = sorted(
        (f for f in root.rglob(f"*{ext}") if not _is_non_public_path(f, root)),
        key=_priority,
    )[:MAX_FILES]
    if header_ext:
        exts = [header_ext] if isinstance(header_ext, str) else header_ext
        for he in exts:
            remaining = MAX_FILES - len(files)
            if remaining <= 0:
                break
            files.extend(sorted(
                (f for f in root.rglob(f"*{he}") if not _is_non_public_path(f, root)),
                key=_priority,
            )[:remaining])
    return files


# ---------------------------------------------------------------------------
# Base class extraction
# ---------------------------------------------------------------------------

def _extract_bases(node, language: str) -> list[str]:
    """Extract base classes / interfaces from a class declaration."""
    bases: list[str] = []
    if language == "python":
        arg_list = find_child_by_type(node, "argument_list")
        if arg_list:
            for ch in arg_list.children:
                if ch.type in ("identifier", "attribute"):
                    bases.append(node_text(ch))
        return bases

    # Java/C#: superclass, interfaces, base_list
    for ch in node.children:
        if ch.type in ("superclass", "type_identifier", "base_list",
                        "super_interfaces", "extends_interfaces",
                        "class_heritage", "extends_clause",
                        "implements_clause"):
            text = node_text(ch)
            # strip keywords
            text = re.sub(r"^(extends|implements|:)\s*", "", text)
            for part in text.split(","):
                part = part.strip()
                if part:
                    bases.append(part)
    return bases


# ---------------------------------------------------------------------------
# Enum member extraction
# ---------------------------------------------------------------------------

def _extract_enum_members(node, language: str) -> list[dict[str, str]]:
    """Extract enum constant names and values."""
    members: list[dict[str, str]] = []
    body = (find_child_by_type(node, "enum_body")
            or find_child_by_type(node, "enum_member_declaration_list")
            or find_child_by_type(node, "enum_declaration_list")
            or find_child_by_type(node, "enumerator_list")
            or find_child_by_type(node, "declaration_list")
            or find_child_by_type(node, "block"))
    if body is None:
        body = node

    for ch in body.children:
        if ch.type in ("enum_constant", "enum_member_declaration",
                        "enum_assignment", "enumerator", "property_identifier"):
            name = _node_name(ch, language) or node_text(ch).strip()
            val_node = child_by_field(ch, "value")
            val = node_text(val_node) if val_node else ""
            if name and name not in ("{", "}", ","):
                members.append({"name": name, "value": val})
    return members


def _extract_python_enum_members(node) -> list[dict[str, str]]:
    """Extract enum members from Python enum class (class-level assignments)."""
    members: list[dict[str, str]] = []
    body = find_child_by_type(node, "block")
    if not body:
        return members
    for ch in body.children:
        # Assignments may appear directly or wrapped in expression_statement
        if ch.type == "expression_statement":
            expr = ch.children[0] if ch.children else None
            if not expr or expr.type != "assignment":
                continue
        elif ch.type == "assignment":
            expr = ch
        else:
            continue
        lhs = child_by_field(expr, "left")
        rhs = child_by_field(expr, "right")
        if lhs and lhs.type == "identifier":
            name = node_text(lhs)
            if not name.startswith("_"):
                val = node_text(rhs) if rhs else ""
                members.append({"name": name, "value": val})
    return members
