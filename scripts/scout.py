#!/usr/bin/env python3
"""scout.py — Tree-sitter extraction engine for FOSS repositories.

Extracts API surface, format support, limitations, code examples, and
structured claims from source repositories across Python, .NET, Java,
C++, TypeScript, and JavaScript platforms.

Usage:
    python scripts/scout.py {family} {platform} {repo-path} {output-dir}

Dependencies:
    tree-sitter>=0.25, tree-sitter-language-pack>=0.13,
    tree-sitter-c-sharp>=0.23, pyyaml
"""

from __future__ import annotations

import argparse
import datetime
import hashlib
import json
import logging
import os
import re
import subprocess
import sys
from pathlib import Path
from typing import Any

import yaml

# ---------------------------------------------------------------------------
# Constants
# ---------------------------------------------------------------------------

LOG = logging.getLogger("scout")

PLATFORM_TO_LANG: dict[str, str] = {
    "python": "python",
    "dotnet": "csharp",
    "java": "java",
    "cpp": "cpp",
    "typescript": "typescript",
    "javascript": "javascript",
    "nodejs": "javascript",
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
    "cpp": set(),
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
}

_FILE_EXTENSIONS: dict[str, str] = {
    "python": ".py",
    "csharp": ".cs",
    "java": ".java",
    "cpp": ".cpp",
    "typescript": ".ts",
    "javascript": ".js",
}

_HEADER_EXTENSIONS: dict[str, str] = {
    "cpp": ".h",
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

MAX_FILES = 500
MAX_SNIPPETS = 100

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
# Package root detection
# ---------------------------------------------------------------------------

def detect_package_root(repo: Path, platform: str) -> Path:
    """Return the package source root inside *repo*."""
    if platform == "python":
        return _detect_python_root(repo)
    if platform == "dotnet":
        return _detect_dotnet_root(repo)
    if platform == "java":
        return _detect_java_root(repo)
    if platform in ("typescript", "javascript", "nodejs"):
        return _detect_js_root(repo, platform)
    if platform == "cpp":
        return _detect_cpp_root(repo)
    return repo


def _detect_python_root(repo: Path) -> Path:
    for marker in ("pyproject.toml", "setup.py", "setup.cfg"):
        if (repo / marker).exists():
            # look for src layout first
            src = repo / "src"
            if src.is_dir():
                pkgs = [d for d in src.iterdir() if d.is_dir()
                        and (d / "__init__.py").exists()]
                if pkgs:
                    return pkgs[0]
            # flat layout: first package dir at root
            pkgs = [d for d in repo.iterdir() if d.is_dir()
                    and (d / "__init__.py").exists()
                    and not d.name.startswith((".", "test", "example", "doc"))]
            if pkgs:
                return pkgs[0]
    return repo


def _detect_dotnet_root(repo: Path) -> Path:
    csproj_files = list(repo.rglob("*.csproj"))[:50]
    if not csproj_files:
        return repo
    # exclude test and exe projects
    candidates = []
    for cp in csproj_files:
        text = cp.read_text(encoding="utf-8", errors="replace").lower()
        if "test" in cp.stem.lower():
            continue
        if "<outputtype>exe</outputtype>" in text:
            continue
        candidates.append(cp)
    if not candidates:
        candidates = csproj_files
    # prefer shortest path (most likely the primary library project)
    candidates.sort(key=lambda p: len(p.parts))
    return candidates[0].parent


def _detect_java_root(repo: Path) -> Path:
    for candidate in ("src/main/java", "app/src/main/java", "src"):
        p = repo / candidate
        if p.is_dir():
            return p
    return repo


def _detect_js_root(repo: Path, platform: str) -> Path:
    pkg_json = repo / "package.json"
    if pkg_json.exists():
        try:
            data = json.loads(pkg_json.read_text(encoding="utf-8", errors="replace"))
            for field in ("main", "module"):
                val = data.get(field, "")
                if val:
                    p = repo / val
                    if p.exists():
                        return p.parent
            exports = data.get("exports", {})
            if isinstance(exports, dict):
                dot = exports.get(".", {})
                if isinstance(dot, dict):
                    for key in ("import", "require", "default"):
                        val = dot.get(key, "")
                        if val and (repo / val).exists():
                            return (repo / val).parent
                elif isinstance(dot, str) and (repo / dot).exists():
                    return (repo / dot).parent
        except (json.JSONDecodeError, OSError):
            pass
    for d in ("src", "lib", "dist"):
        if (repo / d).is_dir():
            return repo / d
    return repo


def _detect_cpp_root(repo: Path) -> Path:
    inc = repo / "include"
    if inc.is_dir():
        return inc
    src = repo / "src"
    if src.is_dir():
        return src
    return repo


# ---------------------------------------------------------------------------
# Manifest parsing
# ---------------------------------------------------------------------------

def parse_manifest(repo: Path, platform: str) -> dict[str, Any]:
    """Extract identity fields from the platform manifest."""
    if platform == "python":
        return _parse_python_manifest(repo)
    if platform == "dotnet":
        return _parse_dotnet_manifest(repo)
    if platform == "java":
        return _parse_java_manifest(repo)
    if platform in ("typescript", "javascript", "nodejs"):
        return _parse_js_manifest(repo)
    if platform == "cpp":
        return _parse_cpp_manifest(repo)
    return {}


def _parse_python_manifest(repo: Path) -> dict[str, Any]:
    info: dict[str, Any] = {}
    pyp = repo / "pyproject.toml"
    if pyp.exists():
        try:
            if sys.version_info >= (3, 11):
                import tomllib
            else:
                import tomli as tomllib  # type: ignore[no-redef]
            data = tomllib.loads(pyp.read_text(encoding="utf-8", errors="replace"))
            proj = data.get("project", {})
            info["name"] = proj.get("name", "")
            info["version"] = proj.get("version", "")
            lic = proj.get("license", "")
            if isinstance(lic, dict):
                lic = lic.get("text", lic.get("file", ""))
            info["license"] = lic
            info["dependencies"] = proj.get("dependencies", [])
            info["requires_python"] = proj.get("requires-python", "")
        except Exception as exc:
            LOG.warning("pyproject.toml parse error: %s", exc)
    if not info.get("name"):
        sp = repo / "setup.py"
        if sp.exists():
            text = sp.read_text(encoding="utf-8", errors="replace")
            m = re.search(r'name\s*=\s*["\']([^"\']+)', text)
            if m:
                info["name"] = m.group(1)
            m = re.search(r'version\s*=\s*["\']([^"\']+)', text)
            if m:
                info["version"] = m.group(1)
    return info


def _parse_dotnet_manifest(repo: Path) -> dict[str, Any]:
    info: dict[str, Any] = {}
    csproj_files = list(repo.rglob("*.csproj"))[:20]
    if not csproj_files:
        return info
    csproj_files.sort(key=lambda p: len(p.parts))
    text = csproj_files[0].read_text(encoding="utf-8", errors="replace")
    for tag, key in [("PackageId", "name"), ("AssemblyName", "name"),
                     ("Version", "version"), ("TargetFramework", "target_framework")]:
        if key in info and info[key]:
            continue
        m = re.search(rf"<{tag}>(.*?)</{tag}>", text)
        if m:
            info[key] = m.group(1)
    return info


def _parse_java_manifest(repo: Path) -> dict[str, Any]:
    info: dict[str, Any] = {}
    pom = repo / "pom.xml"
    if pom.exists():
        text = pom.read_text(encoding="utf-8", errors="replace")
        for tag, key in [("groupId", "group_id"), ("artifactId", "artifact_id"),
                         ("version", "version")]:
            m = re.search(rf"<{tag}>(.*?)</{tag}>", text)
            if m:
                info[key] = m.group(1)
        info["name"] = info.get("artifact_id", "")
        # Extract Java compiler target version (priority: release > target > source)
        for prop_tag in ["maven.compiler.release", "maven.compiler.target", "maven.compiler.source"]:
            m = re.search(rf"<{re.escape(prop_tag)}>(.*?)</{re.escape(prop_tag)}>", text)
            if m:
                info["runtime_min_version"] = m.group(1).strip()
                break
    gradle = repo / "build.gradle"
    if not info.get("name") and gradle.exists():
        text = gradle.read_text(encoding="utf-8", errors="replace")
        m = re.search(r"group\s*=\s*['\"]([^'\"]+)", text)
        if m:
            info["group_id"] = m.group(1)
        m = re.search(r"version\s*=\s*['\"]([^'\"]+)", text)
        if m:
            info["version"] = m.group(1)
    if "runtime_min_version" not in info and gradle.exists():
        text = gradle.read_text(encoding="utf-8", errors="replace")
        for pattern in [
            r"targetCompatibility\s*=\s*['\"]?(\d+)['\"]?",
            r"sourceCompatibility\s*=\s*['\"]?(\d+)['\"]?",
            r"languageVersion\.of\((\d+)\)",
        ]:
            m = re.search(pattern, text)
            if m:
                info["runtime_min_version"] = m.group(1).strip()
                break
    return info


def _parse_js_manifest(repo: Path) -> dict[str, Any]:
    info: dict[str, Any] = {}
    pkg = repo / "package.json"
    if pkg.exists():
        try:
            data = json.loads(pkg.read_text(encoding="utf-8", errors="replace"))
            info["name"] = data.get("name", "")
            info["version"] = data.get("version", "")
            info["license"] = data.get("license", "")
            info["dependencies"] = list((data.get("dependencies") or {}).keys())
            info["engines_node"] = (data.get("engines") or {}).get("node", "")
        except (json.JSONDecodeError, OSError):
            pass
    return info


def _parse_cpp_manifest(repo: Path) -> dict[str, Any]:
    info: dict[str, Any] = {}
    cmake = repo / "CMakeLists.txt"
    if cmake.exists():
        text = cmake.read_text(encoding="utf-8", errors="replace")
        m = re.search(r"project\s*\(\s*(\S+)(?:\s+VERSION\s+(\S+))?", text)
        if m:
            info["name"] = m.group(1)
            if m.group(2):
                info["version"] = m.group(2)
    return info


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


# ---------------------------------------------------------------------------
# Method parameter extraction
# ---------------------------------------------------------------------------

def _extract_method_params(node, language: str) -> list[dict[str, str]]:
    """Extract parameters from a method/function node."""
    params: list[dict[str, str]] = []
    param_list = (child_by_field(node, "parameters")
                  or find_child_by_type(node, "formal_parameters")
                  or find_child_by_type(node, "parameter_list")
                  or find_child_by_type(node, "parameters"))
    if param_list is None:
        return params

    for ch in param_list.children:
        if ch.type in ("formal_parameter", "parameter", "required_parameter",
                        "optional_parameter", "typed_parameter",
                        "default_parameter", "typed_default_parameter",
                        "identifier"):
            pname = ""
            ptype = ""

            name_node = child_by_field(ch, "name")
            if name_node:
                pname = node_text(name_node)
            elif ch.type == "identifier":
                pname = node_text(ch)
            else:
                for sub in ch.children:
                    if sub.type == "identifier":
                        pname = node_text(sub)
                        break

            if pname in ("self", "this", "cls"):
                continue

            type_node = (child_by_field(ch, "type")
                         or find_child_by_type(ch, "type_annotation")
                         or find_child_by_type(ch, "type_identifier")
                         or find_child_by_type(ch, "predefined_type"))
            if type_node:
                ptype = node_text(type_node).lstrip(":").strip()

            if pname:
                params.append({"name": pname, "type": ptype})
    return params


# ---------------------------------------------------------------------------
# Return type extraction
# ---------------------------------------------------------------------------

def _extract_return_type(node, language: str) -> str:
    """Extract the return type from a method/function node."""
    rt = child_by_field(node, "return_type")
    if rt:
        txt = node_text(rt).lstrip(":").strip()
        if txt.startswith("->"):
            txt = txt[2:].strip()
        return txt

    # type annotation after parameters (TS/Python)
    ta = find_child_by_type(node, "type_annotation")
    if ta:
        return node_text(ta).lstrip(":").strip()

    # C#/Java: type before method name
    if language in ("csharp", "java"):
        type_node = child_by_field(node, "type")
        if type_node:
            return node_text(type_node)

    # Go: bare type node after parameter_list
    if language == "go":
        found_params = False
        for ch in node.children:
            if ch.type == "parameter_list":
                found_params = True
                continue
            if found_params and ch.type not in ("{", "block"):
                return node_text(ch)
    return ""


# ---------------------------------------------------------------------------
# Doc comment extraction
# ---------------------------------------------------------------------------

def _extract_doc_comment(node, language: str) -> str:
    """Extract the first sentence of a doc comment preceding *node*."""
    style = _DOC_COMMENT_STYLES.get(language, "javadoc")

    if style == "docstring" and language == "python":
        body = child_by_field(node, "body") or find_child_by_type(node, "block")
        if body and body.children:
            first = body.children[0]
            if first.type == "expression_statement" and first.children:
                s = first.children[0]
                if s.type == "string" or s.type == "concatenated_string":
                    raw = node_text(s).strip("\"' \n\r")
                    return _first_sentence(raw)
        return ""

    # Look at previous sibling for comment
    prev = node.prev_named_sibling
    if prev is None:
        prev = node.prev_sibling
    if prev is None:
        return ""

    txt = node_text(prev)
    if style == "javadoc" or style == "jsdoc":
        if txt.startswith("/**"):
            cleaned = re.sub(r"/\*\*|\*/|\n\s*\*\s?", " ", txt).strip()
            return _first_sentence(cleaned)
    elif style == "xml_doc":
        if txt.strip().startswith("///"):
            lines = txt.strip().splitlines()
            cleaned = " ".join(l.lstrip("/ ").strip() for l in lines)
            # strip XML tags
            cleaned = re.sub(r"<[^>]+>", "", cleaned).strip()
            return _first_sentence(cleaned)
    elif style == "godoc":
        if txt.strip().startswith("//"):
            lines = txt.strip().splitlines()
            cleaned = " ".join(l.lstrip("/ ").strip() for l in lines)
            return _first_sentence(cleaned)

    return ""


def _first_sentence(text: str) -> str:
    """Return the first sentence (up to first period-space or newline)."""
    text = text.strip()
    m = re.match(r"^(.+?[.!?])(?:\s|$)", text, re.DOTALL)
    if m:
        return m.group(1).strip()
    # no sentence-ending punctuation; return first line
    return text.split("\n")[0].strip()[:200]


# ---------------------------------------------------------------------------
# Base class / interface extraction
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
                        "super_interfaces", "class_heritage", "extends_clause",
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


# ---------------------------------------------------------------------------
# Core extraction
# ---------------------------------------------------------------------------

def _collect_source_files(root: Path, ext: str, header_ext: str = "") -> list[Path]:
    """Glob for source files, capped at MAX_FILES."""
    files = list(root.rglob(f"*{ext}"))[:MAX_FILES]
    if header_ext:
        files.extend(list(root.rglob(f"*{header_ext}"))[:MAX_FILES - len(files)])
    return files


class Scout:
    """Main extraction engine."""

    def __init__(self, family: str, platform: str, repo: Path, output: Path):
        self.family = family
        self.platform = platform
        self.repo = repo
        self.output = output
        self.language = PLATFORM_TO_LANG[platform]
        self.parser = get_parser(self.language)
        self.pkg_root = detect_package_root(repo, platform)
        self.manifest = parse_manifest(repo, platform)
        self.classes: list[dict[str, Any]] = []
        self.claims: list[dict[str, Any]] = []
        self.formats: list[dict[str, Any]] = []
        self.limitations: list[dict[str, Any]] = []
        self.snippets: list[dict[str, Any]] = []
        self.class_graph: list[dict[str, Any]] = []
        self.coverage: list[dict[str, Any]] = []
        self.packages: set[str] = set()
        self.scanned_files: list[str] = []
        self.constants: list[dict[str, Any]] = []

    # -- claim helpers -----------------------------------------------------

    def _claim_id(self, text: str) -> str:
        h = hashlib.sha256(text.encode("utf-8")).hexdigest()[:6]
        return f"CLM-{self.family}-{h}"

    def _add_claim(self, kind: str, text: str, file: str = "", line: int = 0):
        cid = self._claim_id(text)
        evidence = []
        if file:
            evidence.append({"file": file, "line": line})
        self.claims.append({
            "claim_id": cid,
            "kind": kind,
            "text": text,
            "confidence": 1.0,
            "claim_source": "scout",
            "evidence": evidence,
        })

    # -- main pipeline -----------------------------------------------------

    def run(self):
        LOG.info("Extracting %s/%s from %s", self.family, self.platform, self.repo)
        LOG.info("Package root: %s", self.pkg_root)

        self._extract_api_surface()
        self._enrich_docstrings()
        self._detect_formats()
        self._detect_limitations()
        self._extract_snippets()
        self._build_identity_claims()
        self._build_class_graph()
        self._build_coverage()
        if self.language == "python":
            self._extract_python_constants()
        self._write_outputs()

    # -- API surface -------------------------------------------------------

    def _extract_api_surface(self):
        ext = _FILE_EXTENSIONS.get(self.language, ".py")
        header_ext = _HEADER_EXTENSIONS.get(self.language, "")
        files = _collect_source_files(self.pkg_root, ext, header_ext)
        LOG.info("Scanning %d source files", len(files))

        class_types = _CLASS_TYPES.get(self.language, set())
        func_types = _FUNC_TYPES.get(self.language, set())

        for fpath in files:
            rel = str(fpath.relative_to(self.repo)).replace("\\", "/")
            try:
                src = fpath.read_bytes()
            except OSError:
                continue

            tree = self.parser.parse(src)
            root = tree.root_node
            self.scanned_files.append(rel)

            # Track packages/namespaces
            module_types = _MODULE_TYPES.get(self.language, set())
            for mnode in collect_nodes(root, module_types):
                pkg_text = node_text(mnode).strip().rstrip(";").rstrip("{").strip()
                # Remove leading keyword (e.g., "package com.foo" → "com.foo")
                for kw in ("package", "namespace"):
                    if pkg_text.startswith(kw):
                        pkg_text = pkg_text[len(kw):].strip()
                if pkg_text:
                    self.packages.add(pkg_text)

            class_nodes = collect_nodes(root, class_types)

            for cnode in class_nodes:
                if not is_public(cnode, self.language):
                    continue

                cname = _node_name(cnode, self.language)
                if not cname:
                    continue

                # Skip C++ forward declarations (class Foo;) — no body
                if (self.language == "cpp"
                        and cnode.type in ("class_specifier", "struct_specifier")
                        and find_child_by_type(cnode, "field_declaration_list") is None):
                    continue

                is_enum = cnode.type in ("enum_declaration", "enum_definition",
                                        "enum_specifier")
                cdoc = _extract_doc_comment(cnode, self.language)
                bases = _extract_bases(cnode, self.language)

                # Python: detect enums by base class inheritance
                if not is_enum and self.language == "python":
                    if set(bases) & _PY_ENUM_BASES:
                        is_enum = True

                if is_enum:
                    if self.language == "python":
                        enum_members = _extract_python_enum_members(cnode)
                    else:
                        enum_members = _extract_enum_members(cnode, self.language)
                elif self.language == "python":
                    # Convention-based enum detection: plain classes whose
                    # body consists entirely of ALL_CAPS assignments are
                    # treated as enum-like (common in 3D/Python libraries).
                    candidates = _extract_python_enum_members(cnode)
                    if candidates and all(
                        m["name"].replace("_", "").isupper()
                        for m in candidates
                    ):
                        enum_members = candidates
                        is_enum = True
                    else:
                        enum_members = []
                else:
                    enum_members = []

                methods: list[dict[str, Any]] = []
                properties: list[dict[str, Any]] = []

                method_nodes = collect_nodes(cnode, func_types)
                for mnode in method_nodes:
                    if not is_public(mnode, self.language):
                        continue
                    mname = _node_name(mnode, self.language)
                    if not mname:
                        continue

                    if mnode.type in ("property_declaration",
                                      "public_field_definition",
                                      "property_signature"):
                        ptype = ""
                        type_node = child_by_field(mnode, "type")
                        if type_node:
                            ptype = node_text(type_node)
                        properties.append({
                            "name": mname,
                            "type": ptype,
                            "line": mnode.start_point[0] + 1,
                        })
                        self._add_claim(
                            "api_method",
                            f"{cname}.{mname} property of type {ptype}",
                            rel, mnode.start_point[0] + 1)
                        continue

                    params = _extract_method_params(mnode, self.language)
                    ret = _extract_return_type(mnode, self.language)
                    mdoc = _extract_doc_comment(mnode, self.language)

                    is_ctor = (mnode.type == "constructor_declaration"
                               or (self.language == "python" and mname == "__init__")
                               or (self.language in ("typescript", "javascript")
                                   and mname == "constructor"))

                    methods.append({
                        "name": mname,
                        "params": params,
                        "return_type": ret,
                        "doc": mdoc,
                        "line": mnode.start_point[0] + 1,
                        "is_constructor": is_ctor,
                    })
                    self._add_claim(
                        "api_method",
                        f"{cname}.{mname}({', '.join(p['name'] for p in params)}) -> {ret}",
                        rel, mnode.start_point[0] + 1)

                # Python properties via decorators
                if self.language == "python":
                    self._extract_python_properties(cnode, cname, rel, properties)
                    # Python dataclass fields (typed class-body annotations)
                    self._extract_python_dataclass_fields(cnode, cname, rel, properties)

                # Java properties via getter/setter synthesis
                if self.language == "java":
                    self._synthesize_java_properties(methods, cname, rel, properties)

                # C++ field_declaration method declarations (no body)
                if self.language == "cpp":
                    body = find_child_by_type(cnode, "field_declaration_list")
                    if body:
                        access = "public" if cnode.type == "struct_specifier" else "private"
                        for member in body.children:
                            if member.type == "access_specifier":
                                access = node_text(member).strip().rstrip(":")
                            elif member.type == "field_declaration" and access == "public":
                                fdecl = find_child_by_type(member, "function_declarator")
                                if fdecl is None:
                                    continue
                                mname = ""
                                for ch in fdecl.children:
                                    if ch.type in ("identifier", "field_identifier"):
                                        mname = node_text(ch)
                                        break
                                if not mname:
                                    continue
                                params = _extract_method_params(fdecl, self.language)
                                ret = _extract_return_type(member, self.language)
                                mdoc = _extract_doc_comment(member, self.language)
                                methods.append({
                                    "name": mname,
                                    "params": params,
                                    "return_type": ret,
                                    "doc": mdoc,
                                    "line": member.start_point[0] + 1,
                                    "is_constructor": False,
                                })
                                self._add_claim(
                                    "api_method",
                                    f"{cname}.{mname}({', '.join(p['name'] for p in params)}) -> {ret}",
                                    rel, member.start_point[0] + 1)

                cls_record: dict[str, Any] = {
                    "name": cname,
                    "kind": cnode.type,
                    "doc": cdoc,
                    "file": rel,
                    "line": cnode.start_point[0] + 1,
                    "bases": bases,
                    "methods": methods,
                    "properties": properties,
                }
                if is_enum:
                    cls_record["enum_members"] = enum_members

                self.classes.append(cls_record)
                self._add_claim("api_class",
                                f"Class {cname} defined in {rel}",
                                rel, cnode.start_point[0] + 1)

            # top-level functions (not inside classes)
            top_funcs = collect_nodes(root, func_types)
            for fnode in top_funcs:
                # skip if nested inside a class
                parent = fnode.parent
                in_class = False
                while parent:
                    if parent.type in class_types:
                        in_class = True
                        break
                    parent = parent.parent
                if in_class:
                    continue
                if not is_public(fnode, self.language):
                    continue
                fname = _node_name(fnode, self.language)
                if not fname:
                    continue
                params = _extract_method_params(fnode, self.language)
                ret = _extract_return_type(fnode, self.language)
                fdoc = _extract_doc_comment(fnode, self.language)

                self.classes.append({
                    "name": fname,
                    "kind": "function",
                    "doc": fdoc,
                    "file": rel,
                    "line": fnode.start_point[0] + 1,
                    "bases": [],
                    "methods": [],
                    "properties": [],
                    "params": params,
                    "return_type": ret,
                })
                self._add_claim("api_method",
                                f"Function {fname}({', '.join(p['name'] for p in params)}) -> {ret}",
                                rel, fnode.start_point[0] + 1)

    def _extract_python_properties(self, cnode, cname: str, rel: str,
                                   properties: list[dict[str, Any]]):
        """Extract @property decorated methods in Python classes."""
        func_nodes = collect_nodes(cnode, {"function_definition"})

        # First pass: collect all setter names in this class
        setter_names: set[str] = set()
        for fn in func_nodes:
            dec = find_child_by_type(fn, "decorator")
            if dec is None:
                prev = fn.prev_named_sibling
                if prev and prev.type == "decorator":
                    dec = prev
            if dec is None:
                continue
            dec_text = node_text(dec)
            # Match @name.setter pattern
            if re.search(r"@\w+\.setter", dec_text):
                setter_name = _node_name(fn, "python")
                if setter_name:
                    setter_names.add(setter_name)

        for fn in func_nodes:
            # check for @property decorator
            dec = find_child_by_type(fn, "decorator")
            if dec is None:
                # check previous sibling
                prev = fn.prev_named_sibling
                if prev and prev.type == "decorator":
                    dec = prev
            if dec is None:
                continue
            dec_text = node_text(dec)
            if "@property" not in dec_text:
                continue
            pname = _node_name(fn, "python")
            if not pname or pname.startswith("_"):
                continue
            ret = _extract_return_type(fn, "python")
            properties.append({
                "name": pname,
                "type": ret,
                "line": fn.start_point[0] + 1,
                "read_write": pname in setter_names,
            })
            self._add_claim("api_method",
                            f"{cname}.{pname} property of type {ret}",
                            rel, fn.start_point[0] + 1)

    def _extract_python_dataclass_fields(self, cnode, cname: str, rel: str,
                                        properties: list[dict[str, Any]]):
        """Extract typed fields from @dataclass decorated Python classes.

        Scans the class decorators for 'dataclass' and then extracts class-body
        annotated assignments of the form ``name: type [= default]``.
        Skips names starting with ``_``.
        """
        # Check if this class has a @dataclass decorator.
        # In tree-sitter Python, when a class has decorators the AST is:
        #   decorated_definition -> [decorator, class_definition]
        # The decorator is NOT a child of class_definition but of its parent.
        is_dataclass = False

        # Check parent node (decorated_definition) for @dataclass
        parent = cnode.parent
        if parent and parent.type == "decorated_definition":
            for ch in parent.children:
                if ch.type == "decorator" and "dataclass" in node_text(ch):
                    is_dataclass = True
                    break

        # Fallback: check direct children of class node
        if not is_dataclass:
            for ch in cnode.children:
                if ch.type == "decorator" and "dataclass" in node_text(ch):
                    is_dataclass = True
                    break

        # Fallback: check previous sibling decorators
        if not is_dataclass:
            prev = cnode.prev_named_sibling
            while prev and prev.type == "decorator":
                if "dataclass" in node_text(prev):
                    is_dataclass = True
                    break
                prev = prev.prev_named_sibling

        if not is_dataclass:
            return

        existing_names = {p["name"] for p in properties}
        body = find_child_by_type(cnode, "block")
        if not body:
            return

        for stmt in body.children:
            # Resolve the actual assignment/annotation node
            # In tree-sitter Python, typed fields ``name: type [= default]``
            # appear as ``assignment`` nodes with a ``type`` child field.
            # They may also appear as ``annotated_assignment`` or be wrapped
            # in ``expression_statement``.
            _assign = None
            if stmt.type == "assignment":
                _assign = stmt
            elif stmt.type == "annotated_assignment":
                _assign = stmt
            elif stmt.type == "expression_statement":
                inner = stmt.children[0] if stmt.children else None
                if inner and inner.type in ("assignment", "annotated_assignment"):
                    _assign = inner
            elif stmt.type == "typed_parameter":
                # Some tree-sitter grammars use typed_parameter at class body
                name_node = find_child_by_type(stmt, "identifier") or child_by_field(stmt, "name")
                if name_node:
                    fname = node_text(name_node)
                    if fname and not fname.startswith("_") and fname not in existing_names:
                        type_node = child_by_field(stmt, "type") or find_child_by_type(stmt, "type")
                        ftype = node_text(type_node).lstrip(":").strip() if type_node else ""
                        properties.append({"name": fname, "type": ftype, "kind": "field",
                                           "line": stmt.start_point[0] + 1})
                        existing_names.add(fname)
                continue

            if _assign is None:
                continue

            # Extract name from left/first identifier child
            lhs = child_by_field(_assign, "left") or (_assign.children[0] if _assign.children else None)
            if not lhs or lhs.type != "identifier":
                continue
            fname = node_text(lhs)
            if not fname or fname.startswith("_") or fname in existing_names:
                continue

            # Extract type annotation
            type_node = child_by_field(_assign, "type") or find_child_by_type(_assign, "type")
            ftype = node_text(type_node).lstrip(":").strip() if type_node else ""
            # Only add if there IS a type annotation (otherwise it's not a dataclass field)
            properties.append({"name": fname, "type": ftype, "kind": "field",
                               "line": stmt.start_point[0] + 1})
            existing_names.add(fname)

    _JAVA_OBJECT_METHODS = frozenset({
        "getClass", "hashCode", "equals", "toString",
        "notify", "notifyAll", "wait", "clone", "finalize",
    })

    def _synthesize_java_properties(self, methods, cname: str, rel: str,
                                    properties: list[dict[str, Any]]):
        """Synthesize property entries from Java getter/setter method pairs."""
        getters: dict[str, dict[str, Any]] = {}
        for m in methods:
            name = m["name"]
            if name in self._JAVA_OBJECT_METHODS:
                continue
            params = m.get("params", [])
            if (name.startswith("get") and len(name) > 3
                    and name[3].isupper() and len(params) == 0):
                prop_name = name[3].lower() + name[4:]
                getters[prop_name] = m
            elif (name.startswith("is") and len(name) > 2
                  and name[2].isupper() and len(params) == 0):
                prop_name = name[2].lower() + name[3:]
                getters[prop_name] = m
        for prop_name, getter in getters.items():
            ptype = getter.get("return_type", "")
            properties.append({
                "name": prop_name,
                "type": ptype,
                "line": getter["line"],
            })
            self._add_claim("api_method",
                            f"{cname}.{prop_name} property of type {ptype}",
                            rel, getter["line"])

    # -- Docstring enrichment -----------------------------------------------

    def _enrich_docstrings(self):
        """Post-process extracted classes with platform-specific docstring enrichers.

        Populates empty ``doc`` fields on class/method records using
        Javadoc (Java), Doxygen (C++), or XML doc comments (.NET/C#).
        """
        try:
            import importlib
            spec = importlib.util.spec_from_file_location(
                "scout_enrichers",
                Path(__file__).resolve().parent / "pipeline" / "scout_enrichers" / "__init__.py",
            )
            if spec is None or spec.loader is None:
                return
            mod = importlib.util.module_from_spec(spec)
            spec.loader.exec_module(mod)
            enrich_classes = mod.enrich_classes
        except Exception:
            return

        count = enrich_classes(self.classes, self.repo, self.platform)
        if count:
            LOG.info("Docstring enrichment: populated %d items", count)

    # -- Format detection --------------------------------------------------

    def _detect_formats(self):
        ext = _FILE_EXTENSIONS.get(self.language, ".py")
        files = _collect_source_files(self.pkg_root, ext)
        format_pattern = re.compile(
            r"(FileFormat|FormatType|SupportedFormat|FileType)", re.IGNORECASE)
        importer_pattern = re.compile(
            r"(Importer|Exporter|Reader|Writer|Loader|Saver)", re.IGNORECASE)

        for fpath in files:
            rel = str(fpath.relative_to(self.repo)).replace("\\", "/")
            try:
                text = fpath.read_text(encoding="utf-8", errors="replace")
            except OSError:
                continue

            if not format_pattern.search(text) and not importer_pattern.search(text):
                continue

            tree = self.parser.parse(text.encode("utf-8"))
            root = tree.root_node
            class_types = _CLASS_TYPES.get(self.language, set())
            class_nodes = collect_nodes(root, class_types)

            for cn in class_nodes:
                cname = _node_name(cn, self.language)
                if not cname:
                    continue
                is_enum = cn.type in ("enum_declaration", "enum_definition",
                                      "enum_specifier")
                # Python: detect enums by base class inheritance
                if not is_enum and self.language == "python":
                    fmt_bases = _extract_bases(cn, self.language)
                    if set(fmt_bases) & _PY_ENUM_BASES:
                        is_enum = True

                if format_pattern.search(cname):
                    if is_enum:
                        if self.language == "python":
                            members = _extract_python_enum_members(cn)
                        else:
                            members = _extract_enum_members(cn, self.language)
                        for mem in members:
                            fmt_entry = {
                                "format": mem["name"],
                                "enum": cname,
                                "value": mem.get("value", ""),
                                "file": rel,
                                "line": cn.start_point[0] + 1,
                                "direction": "both",
                            }
                            self.formats.append(fmt_entry)
                            self._add_claim("format_support",
                                            f"Supports format {mem['name']} via {cname}",
                                            rel, cn.start_point[0] + 1)
                    else:
                        self.formats.append({
                            "format": cname,
                            "enum": "",
                            "value": "",
                            "file": rel,
                            "line": cn.start_point[0] + 1,
                            "direction": "both",
                        })

                if importer_pattern.search(cname):
                    direction = "import"
                    if re.search(r"(Exporter|Writer|Saver)", cname, re.IGNORECASE):
                        direction = "export"
                    fmt_name = re.sub(
                        r"(Importer|Exporter|Reader|Writer|Loader|Saver)", "",
                        cname, flags=re.IGNORECASE).strip()
                    if fmt_name:
                        self.formats.append({
                            "format": fmt_name,
                            "enum": "",
                            "value": "",
                            "file": rel,
                            "line": cn.start_point[0] + 1,
                            "direction": direction,
                        })
                        self._add_claim("format_support",
                                        f"{direction} support for {fmt_name} via {cname}",
                                        rel, cn.start_point[0] + 1)

    # -- Limitation detection ----------------------------------------------

    def _detect_limitations(self):
        pattern = _NOT_IMPL_PATTERNS.get(self.language)
        if pattern is None:
            return

        ext = _FILE_EXTENSIONS.get(self.language, ".py")
        files = _collect_source_files(self.pkg_root, ext)

        class_types = _CLASS_TYPES.get(self.language, set())
        func_types = _FUNC_TYPES.get(self.language, set())

        for fpath in files:
            rel = str(fpath.relative_to(self.repo)).replace("\\", "/")
            try:
                text = fpath.read_text(encoding="utf-8", errors="replace")
            except OSError:
                continue

            if not pattern.search(text):
                continue

            src_bytes = text.encode("utf-8")
            tree = self.parser.parse(src_bytes)
            root = tree.root_node

            # find all lines matching the pattern
            for i, line in enumerate(text.splitlines(), 1):
                if not pattern.search(line):
                    continue

                # find enclosing class and method
                enclosing_class = ""
                enclosing_method = ""

                # walk from root to find enclosing context at this line
                byte_offset = sum(len(l.encode("utf-8")) + 1
                                  for l in text.splitlines()[:i - 1])
                node = root.descendant_for_byte_range(byte_offset, byte_offset + 1)
                while node:
                    if node.type in func_types:
                        enclosing_method = _node_name(node, self.language)
                    if node.type in class_types:
                        enclosing_class = _node_name(node, self.language)
                    node = node.parent

                lim = {
                    "file": rel,
                    "line": i,
                    "class": enclosing_class,
                    "method": enclosing_method,
                    "text": line.strip(),
                }
                self.limitations.append(lim)
                self._add_claim(
                    "limitation",
                    f"Not implemented: {enclosing_class}.{enclosing_method} in {rel}:{i}",
                    rel, i)

    # -- Snippet extraction ------------------------------------------------

    def _extract_snippets(self):
        """Extract function-level snippets from test/example directories.

        For each test/example function found, records which API classes and
        methods it references (cross-referenced against self.classes) and
        which file format names appear.  Also extracts README code blocks
        as whole-file snippets.  Capped at MAX_SNIPPETS per product.
        """
        # Build lookup sets from already-extracted api_surface
        api_class_names: set[str] = set()
        api_method_index: dict[str, set[str]] = {}  # class -> methods
        for cls in self.classes:
            cname = cls.get("name", "")
            if not cname or cls.get("kind") == "function":
                continue
            api_class_names.add(cname)
            meths = set()
            for m in cls.get("methods", []):
                if isinstance(m, dict) and m.get("name"):
                    meths.add(m["name"])
            api_method_index[cname] = meths

        # Build format names set from already-extracted formats
        format_names: set[str] = set()
        for fmt in self.formats:
            fname = fmt.get("format", "")
            if fname:
                format_names.add(fname.lower())

        snippet_dirs = ["tests", "test", "examples", "example", "samples",
                        "demo"]
        ext = _FILE_EXTENSIONS.get(self.language, ".py")
        func_types = _FUNC_TYPES.get(self.language, set())
        class_types = _CLASS_TYPES.get(self.language, set())

        # Build search base list: walk from pkg_root up to repo root so that
        # repos with a language subdirectory (e.g. repo/python/tests/) are
        # found even when tests are not at the repo root level.
        _search_bases: list[Path] = []
        _p = self.pkg_root
        while True:
            try:
                _p.relative_to(self.repo)
                _search_bases.append(_p)
            except ValueError:
                pass
            if _p == self.repo or _p.parent == _p:
                break
            _p = _p.parent
        if self.repo not in _search_bases:
            _search_bases.append(self.repo)

        snippet_counter = 0

        for sdir in snippet_dirs:
            _visited: set[Path] = set()
            for _base in _search_bases:
                d = _base / sdir
                if d in _visited:
                    continue
                _visited.add(d)
                if not d.is_dir():
                    continue
                files = sorted(d.rglob(f"*{ext}"))[:MAX_FILES]
                for fpath in files:
                    if snippet_counter >= MAX_SNIPPETS:
                        break
                    rel = str(fpath.relative_to(self.repo)).replace("\\", "/")
                    try:
                        src = fpath.read_bytes()
                    except OSError:
                        continue
                    tree = self.parser.parse(src)
                    text = src.decode("utf-8", errors="replace")
                    text_lines = text.splitlines()
                    root = tree.root_node

                    # Collect candidate function nodes
                    func_nodes = self._collect_snippet_functions(
                        root, func_types, class_types, text)

                    for fn_name, fn_node, fn_line in func_nodes:
                        if snippet_counter >= MAX_SNIPPETS:
                            break
                        code = node_text(fn_node)
                        if not code.strip():
                            continue

                        # Cross-reference: which API classes/methods appear?
                        classes_used: list[str] = []
                        methods_used: list[str] = []
                        formats_ref: list[str] = []

                        code_lower = code.lower()
                        for cname in api_class_names:
                            if cname in code:
                                classes_used.append(cname)
                                for mname in api_method_index.get(cname, set()):
                                    # Look for Class.method or just .method patterns
                                    if (f"{cname}.{mname}" in code
                                            or f".{mname}(" in code):
                                        methods_used.append(f"{cname}.{mname}")

                        for fmt_name in format_names:
                            if fmt_name in code_lower:
                                formats_ref.append(fmt_name)

                        snippet_id = f"snippet_{snippet_counter + 1:03d}"
                        self.snippets.append({
                            "id": snippet_id,
                            "file": f"{snippet_id}{ext}",
                            "source_file": rel,
                            "source_function": fn_name,
                            "source_line": fn_line,
                            "language": self.language,
                            "code": code[:5000],
                            "valid": not fn_node.has_error,
                            "classes_used": sorted(set(classes_used)),
                            "methods_used": sorted(set(methods_used)),
                            "formats_referenced": sorted(set(formats_ref)),
                        })
                        snippet_counter += 1

            if snippet_counter >= MAX_SNIPPETS:
                break

        # README fenced code blocks (as whole-file snippets)
        for readme_name in ("README.md", "readme.md", "README.rst"):
            if snippet_counter >= MAX_SNIPPETS:
                break
            readme = self.repo / readme_name
            if readme.exists():
                try:
                    text = readme.read_text(encoding="utf-8", errors="replace")
                except OSError:
                    continue
                lang_names = {self.language}
                if self.language == "csharp":
                    lang_names.update({"csharp", "cs", "c#"})
                if self.language == "javascript":
                    lang_names.update({"javascript", "js"})
                if self.language == "typescript":
                    lang_names.update({"typescript", "ts"})
                if self.language == "python":
                    lang_names.update({"python", "py"})
                if self.language == "java":
                    lang_names.add("java")
                if self.language == "cpp":
                    lang_names.update({"cpp", "c++"})

                fence_pattern = re.compile(
                    r"```(" + "|".join(re.escape(n) for n in lang_names)
                    + r")\s*\n(.*?)```", re.DOTALL | re.IGNORECASE)
                for m in fence_pattern.finditer(text):
                    if snippet_counter >= MAX_SNIPPETS:
                        break
                    code = m.group(2)
                    t = self.parser.parse(code.encode("utf-8"))
                    valid = not t.root_node.has_error

                    classes_used = [c for c in api_class_names if c in code]
                    methods_used = []
                    for cname in classes_used:
                        for mname in api_method_index.get(cname, set()):
                            if f"{cname}.{mname}" in code or f".{mname}(" in code:
                                methods_used.append(f"{cname}.{mname}")
                    formats_ref = [f for f in format_names if f in code.lower()]

                    snippet_id = f"snippet_{snippet_counter + 1:03d}"
                    self.snippets.append({
                        "id": snippet_id,
                        "file": f"{snippet_id}{ext}",
                        "source_file": readme_name,
                        "source_function": "(readme_block)",
                        "source_line": text[:m.start()].count("\n") + 1,
                        "language": self.language,
                        "code": code[:5000],
                        "valid": valid,
                        "classes_used": sorted(set(classes_used)),
                        "methods_used": sorted(set(methods_used)),
                        "formats_referenced": sorted(set(formats_ref)),
                    })
                    snippet_counter += 1
                break

        LOG.info("Extracted %d function-level snippets", len(self.snippets))

    def _collect_snippet_functions(self, root, func_types, class_types,
                                   source_text):
        """Collect candidate test/example functions from a parsed tree.

        Returns list of (function_name, node, line_number) tuples.
        Language-specific heuristics determine which functions qualify.
        """
        results: list[tuple[str, Any, int]] = []

        if self.language == "python":
            # Functions starting with test_, example_, or demo_
            for fn in collect_nodes(root, func_types):
                fname = _node_name(fn, self.language)
                if fname and (fname.startswith("test_")
                              or fname.startswith("example_")
                              or fname.startswith("demo_")):
                    results.append((fname, fn, fn.start_point[0] + 1))

        elif self.language in ("java", "csharp"):
            # Methods inside test classes (class name contains Test/Tests)
            for cn in collect_nodes(root, class_types):
                cname = _node_name(cn, self.language)
                if not cname:
                    continue
                is_test_class = ("Test" in cname or "Example" in cname
                                 or "Demo" in cname or "Sample" in cname)
                if not is_test_class:
                    continue
                for fn in collect_nodes(cn, func_types):
                    fname = _node_name(fn, self.language)
                    if fname and not fname.startswith("_"):
                        results.append((fname, fn, fn.start_point[0] + 1))

        elif self.language == "cpp":
            # Functions in test files
            for fn in collect_nodes(root, func_types):
                fname = _node_name(fn, self.language)
                if fname and (fname.startswith("test_")
                              or fname.startswith("Test")
                              or fname.startswith("TEST")):
                    results.append((fname, fn, fn.start_point[0] + 1))

        elif self.language in ("typescript", "javascript"):
            # Exported functions, test() / describe() blocks, or
            # functions starting with test/example
            for fn in collect_nodes(root, func_types):
                fname = _node_name(fn, self.language)
                if not fname:
                    continue
                parent = fn.parent
                is_exported = (parent and parent.type == "export_statement")
                is_test_fn = (fname.startswith("test")
                              or fname.startswith("example")
                              or fname.startswith("demo"))
                if is_exported or is_test_fn:
                    results.append((fname, fn, fn.start_point[0] + 1))

            # Also capture describe/test/it call expression blocks
            # These appear as call_expression nodes with string + arrow_function
            _test_block_names = {"test", "it", "describe"}
            for call_node in collect_nodes(root, {"call_expression"}):
                fn_part = child_by_field(call_node, "function")
                if fn_part and node_text(fn_part) in _test_block_names:
                    args = child_by_field(call_node, "arguments")
                    if args and args.children:
                        # First arg is usually the test description string
                        desc = ""
                        for ch in args.children:
                            if ch.type in ("string", "template_string"):
                                desc = node_text(ch).strip("'\"` ")
                                break
                        block_name = desc[:60] or node_text(fn_part)
                        results.append(
                            (block_name, call_node,
                             call_node.start_point[0] + 1))

        return results

    # -- Python constants extraction ----------------------------------------

    def _extract_python_constants(self):
        """Extract UPPER_CASE module-level constants and enum member names from Python files.

        For each Python source file:
        1. Scan for module-level ``NAME = value`` assignments where NAME matches
           ``^[A-Z][A-Z0-9_]+$`` and does not start with ``_``.
        2. Also include UPPER_CASE members from IntEnum / Enum class bodies.
        3. Mark ``exported: True`` if the name appears in the module's ``__all__``.
        """
        _upper_re = re.compile(r"^[A-Z][A-Z0-9_]+$")
        ext = ".py"
        files = _collect_source_files(self.pkg_root, ext)

        seen: set[str] = set()  # (name, source_file) dedup

        for fpath in files:
            rel = str(fpath.relative_to(self.repo)).replace("\\", "/")
            try:
                text = fpath.read_text(encoding="utf-8", errors="replace")
            except OSError:
                continue

            # Determine __all__ for this module
            all_names: set[str] = set()
            all_match = re.search(r"^__all__\s*=\s*\[([^\]]*)\]", text, re.MULTILINE)
            if all_match:
                for m in re.finditer(r'["\'](\w+)["\']', all_match.group(1)):
                    all_names.add(m.group(1))

            try:
                src = fpath.read_bytes()
            except OSError:
                continue
            tree = self.parser.parse(src)
            root = tree.root_node

            class_types = _CLASS_TYPES.get(self.language, set())

            # Module-level assignments (not inside class or function)
            for stmt in root.children:
                # Resolve inner assignment node (may be wrapped or direct)
                assign_node = None
                if stmt.type == "assignment":
                    assign_node = stmt
                elif stmt.type == "expression_statement":
                    inner = stmt.children[0] if stmt.children else None
                    if inner and inner.type == "assignment":
                        assign_node = inner
                elif stmt.type == "annotated_assignment":
                    # name: type = value at module level
                    lhs = child_by_field(stmt, "left") or (stmt.children[0] if stmt.children else None)
                    if lhs and lhs.type == "identifier":
                        name = node_text(lhs)
                        if _upper_re.match(name) and not name.startswith("_"):
                            key = (name, rel)
                            if key not in seen:
                                seen.add(key)
                                rhs = child_by_field(stmt, "value")
                                val = node_text(rhs) if rhs else ""
                                self.constants.append({
                                    "name": name,
                                    "value": val,
                                    "exported": name in all_names,
                                    "source_file": rel,
                                })

                if assign_node is not None:
                    lhs = child_by_field(assign_node, "left")
                    rhs = child_by_field(assign_node, "right")
                    if lhs and lhs.type == "identifier":
                        name = node_text(lhs)
                        if _upper_re.match(name) and not name.startswith("_"):
                            key = (name, rel)
                            if key not in seen:
                                seen.add(key)
                                val = node_text(rhs) if rhs else ""
                                self.constants.append({
                                    "name": name,
                                    "value": val,
                                    "exported": name in all_names,
                                    "source_file": rel,
                                })
                    continue

                # Enum class bodies: UPPER_CASE member names
                # Also handle decorated_definition wrapping a class
                _class_stmt = stmt
                if stmt.type == "decorated_definition":
                    for _dch in stmt.children:
                        if _dch.type in class_types:
                            _class_stmt = _dch
                            break
                if _class_stmt.type in class_types:
                    cname = _node_name(_class_stmt, self.language)
                    bases = _extract_bases(_class_stmt, self.language)
                    if set(bases) & _PY_ENUM_BASES:
                        body = find_child_by_type(_class_stmt, "block")
                        if body:
                            for ch in body.children:
                                # assignment inside enum class body
                                # May be direct assignment or wrapped
                                inner_assign = None
                                if ch.type == "assignment":
                                    inner_assign = ch
                                elif ch.type == "expression_statement" and ch.children:
                                    _inner = ch.children[0]
                                    if _inner.type == "assignment":
                                        inner_assign = _inner
                                if inner_assign is not None:
                                    lhs = child_by_field(inner_assign, "left")
                                    rhs = child_by_field(inner_assign, "right")
                                    if lhs and lhs.type == "identifier":
                                        name = node_text(lhs)
                                        if _upper_re.match(name) and not name.startswith("_"):
                                            key = (name, rel)
                                            if key not in seen:
                                                seen.add(key)
                                                val = node_text(rhs) if rhs else ""
                                                self.constants.append({
                                                    "name": name,
                                                    "value": val,
                                                    "exported": name in all_names,
                                                    "source_file": rel,
                                                })

    # -- Identity claims ---------------------------------------------------

    def _build_identity_claims(self):
        name = self.manifest.get("name", "")
        version = self.manifest.get("version", "")
        lic = self.manifest.get("license", "")

        if name:
            self._add_claim("install",
                            f"Package name is {name}")
        if version:
            self._add_claim("install",
                            f"Current version is {version}")
        if lic:
            self._add_claim("license",
                            f"Licensed under {lic}")

        deps = self.manifest.get("dependencies", [])
        for dep in deps[:50]:
            if isinstance(dep, str):
                self._add_claim("dependency", f"Depends on {dep}")

    # -- Class graph -------------------------------------------------------

    def _build_class_graph(self):
        name_set = {c["name"] for c in self.classes}
        for cls in self.classes:
            if cls.get("bases"):
                for base in cls["bases"]:
                    edge = {
                        "child": cls["name"],
                        "parent": base,
                        "relationship": "inherits",
                        "internal": base in name_set,
                    }
                    self.class_graph.append(edge)

    # -- Coverage matrix ---------------------------------------------------

    def _build_coverage(self):
        for cls in self.classes:
            if cls.get("kind") == "function":
                continue
            self.coverage.append({
                "class": cls["name"],
                "file": cls["file"],
                "method_count": len(cls.get("methods", [])),
                "property_count": len(cls.get("properties", [])),
                "has_doc": bool(cls.get("doc")),
                "has_tests": any(s["file"].startswith(("test", "tests"))
                                for s in self.snippets
                                if cls["name"].lower() in s.get("code", "").lower()),
                "enum_members": len(cls.get("enum_members", [])),
            })

    # -- Output ------------------------------------------------------------

    def _get_repo_sha(self) -> str:
        try:
            result = subprocess.run(
                ["git", "rev-parse", "HEAD"],
                cwd=str(self.repo), capture_output=True, text=True, timeout=10)
            return result.stdout.strip()
        except Exception:
            return ""

    def _get_repo_url(self) -> str:
        """Return the git remote 'origin' URL, or '' if unavailable."""
        try:
            result = subprocess.run(
                ["git", "remote", "get-url", "origin"],
                cwd=str(self.repo),
                capture_output=True, text=True, timeout=10,
            )
            if result.returncode == 0:
                return result.stdout.strip()
        except Exception:
            pass
        return ""

    def _install_command(self) -> str:
        name = self.manifest.get("name", "")
        version = self.manifest.get("version", "")
        if self.platform == "python":
            if name and version:
                return f"pip install {name}>={version}"
            return f"pip install {name}" if name else ""
        if self.platform == "dotnet":
            if name and version:
                return f"dotnet add package {name} --version {version}"
            return f"dotnet add package {name}" if name else ""
        if self.platform == "java":
            gid = self.manifest.get("group_id", "")
            aid = self.manifest.get("artifact_id", "")
            if gid and aid:
                return f"<!-- Maven -->\n<dependency>\n  <groupId>{gid}</groupId>\n  <artifactId>{aid}</artifactId>\n  <version>{version}</version>\n</dependency>"
            return ""
        if self.platform in ("typescript", "javascript", "nodejs"):
            if name and version:
                return f"npm install {name}@{version}"
            return f"npm install {name}" if name else ""
        if self.platform == "cpp":
            return ""
        return ""

    def _canonical_import(self) -> str:
        name = self.manifest.get("name", "")
        if self.platform == "python":
            return name.replace("-", "_") if name else ""
        if self.platform == "dotnet":
            return f"using {name};" if name else ""
        if self.platform == "java":
            gid = self.manifest.get("group_id", "")
            aid = self.manifest.get("artifact_id", "")
            if gid and aid:
                return f"import {gid}.{aid}.*;"
            return ""
        if self.platform in ("typescript", "javascript", "nodejs"):
            return f'import {{ ... }} from "{name}";' if name else ""
        return ""

    def _runtime_requirement(self) -> str:
        if self.platform == "python":
            return self.manifest.get("requires_python", "")
        if self.platform == "dotnet":
            return self.manifest.get("target_framework", "")
        if self.platform in ("typescript", "javascript", "nodejs"):
            return self.manifest.get("engines_node", "")
        if self.platform in ("java", "kotlin"):
            return self.manifest.get("runtime_min_version", "")
        return ""

    def _write_outputs(self):
        self.output.mkdir(parents=True, exist_ok=True)

        # model.yaml
        class_count = sum(1 for c in self.classes if c.get("kind") != "function")
        method_count = sum(len(c.get("methods", [])) for c in self.classes)
        prop_count = sum(len(c.get("properties", [])) for c in self.classes)
        enum_count = sum(1 for c in self.classes if c.get("enum_members") is not None)

        model = {
            "family": self.family,
            "platform": self.platform,
            "product_name": self.manifest.get("name", f"Aspose.{self.family.upper()}-FOSS for {self.platform}"),
            "version": self.manifest.get("version", ""),
            "license": self.manifest.get("license", ""),
            "repo_sha": self._get_repo_sha(),
            "repo_url": self._get_repo_url(),
            "extracted_at": datetime.datetime.now(datetime.timezone.utc).isoformat(),
            "source": "scout",
            "package_root": str(self.pkg_root.relative_to(self.repo)).replace("\\", "/"),
            "canonical_import": self._canonical_import(),
            "install_command": self._install_command(),
            "runtime_requirement": self._runtime_requirement(),
            "stats": {
                "class_count": class_count,
                "method_count": method_count,
                "property_count": prop_count,
                "enum_count": enum_count,
                "format_count": len(self.formats),
                "snippet_count": len(self.snippets),
                "limitation_count": len(self.limitations),
            },
        }
        (self.output / "model.yaml").write_text(
            yaml.dump(model, default_flow_style=False, sort_keys=False,
                      allow_unicode=True),
            encoding="utf-8")
        LOG.info("Wrote model.yaml")

        # api_surface.json
        (self.output / "api_surface.json").write_text(
            json.dumps(self.classes, indent=2, ensure_ascii=False),
            encoding="utf-8")
        LOG.info("Wrote api_surface.json (%d entries)", len(self.classes))

        # claims.json
        (self.output / "claims.json").write_text(
            json.dumps(self.claims, indent=2, ensure_ascii=False),
            encoding="utf-8")
        LOG.info("Wrote claims.json (%d claims)", len(self.claims))

        # formats.json
        (self.output / "formats.json").write_text(
            json.dumps(self.formats, indent=2, ensure_ascii=False),
            encoding="utf-8")
        LOG.info("Wrote formats.json (%d formats)", len(self.formats))

        # limitations.md
        lim_lines = ["# Limitations (Not Implemented)\n"]
        if self.limitations:
            lim_lines.append("| File | Line | Class | Method | Code |")
            lim_lines.append("|------|------|-------|--------|------|")
            for lim in self.limitations:
                lim_lines.append(
                    f"| {lim['file']} | {lim['line']} | {lim['class']} "
                    f"| {lim['method']} | `{lim['text'][:80]}` |")
        else:
            lim_lines.append("No NotImplementedError patterns detected.")
        (self.output / "limitations.md").write_text(
            "\n".join(lim_lines) + "\n", encoding="utf-8")
        LOG.info("Wrote limitations.md (%d entries)", len(self.limitations))

        # install.md
        install_lines = [f"# Install {self.manifest.get('name', self.family)}\n"]
        cmd = self._install_command()
        if cmd:
            install_lines.append("```")
            install_lines.append(cmd)
            install_lines.append("```\n")
        imp = self._canonical_import()
        if imp:
            install_lines.append("## Verify\n")
            install_lines.append("```")
            install_lines.append(imp)
            install_lines.append("```\n")
        (self.output / "install.md").write_text(
            "\n".join(install_lines) + "\n", encoding="utf-8")
        LOG.info("Wrote install.md")

        # class_graph.json
        (self.output / "class_graph.json").write_text(
            json.dumps(self.class_graph, indent=2, ensure_ascii=False),
            encoding="utf-8")
        LOG.info("Wrote class_graph.json (%d edges)", len(self.class_graph))

        # coverage_matrix.json
        (self.output / "coverage_matrix.json").write_text(
            json.dumps(self.coverage, indent=2, ensure_ascii=False),
            encoding="utf-8")
        LOG.info("Wrote coverage_matrix.json (%d entries)", len(self.coverage))

        # constants.json (Python only — written for all platforms as empty list)
        (self.output / "constants.json").write_text(
            json.dumps(self.constants, indent=2, ensure_ascii=False),
            encoding="utf-8")
        LOG.info("Wrote constants.json (%d entries)", len(self.constants))

        # absent_evidence.json — signals what scout scanned so merge.py can
        # reject FL-only classes that scout explicitly did NOT find.
        absent_evidence = {
            "scan_complete": True,
            "scanned_file_count": len(self.scanned_files),
            "scanned_packages": sorted(self.packages),
            "found_classes": sorted(
                c["name"] for c in self.classes if c.get("kind") != "function"
            ),
            "found_enums": sorted(
                c["name"] for c in self.classes
                if c.get("kind") in ("enum_declaration", "enum_definition")
            ),
        }
        (self.output / "absent_evidence.json").write_text(
            json.dumps(absent_evidence, indent=2, ensure_ascii=False),
            encoding="utf-8")
        LOG.info("Wrote absent_evidence.json (%d classes, %d packages)",
                 len(absent_evidence["found_classes"]),
                 len(absent_evidence["scanned_packages"]))

        # snippets/
        snippets_dir = self.output / "snippets"
        snippets_dir.mkdir(exist_ok=True)
        ext = _FILE_EXTENSIONS.get(self.language, ".txt")
        index_entries: list[dict[str, Any]] = []
        for snip in self.snippets:
            snippet_id = snip.get("id", "")
            out_fname = snip.get("file", f"{snippet_id}{ext}")
            out_path = snippets_dir / out_fname
            out_path.write_text(snip.get("code", ""), encoding="utf-8")
            index_entries.append({
                "id": snippet_id,
                "file": out_fname,
                "source_file": snip.get("source_file", ""),
                "source_function": snip.get("source_function", ""),
                "source_line": snip.get("source_line", 0),
                "classes_used": snip.get("classes_used", []),
                "methods_used": snip.get("methods_used", []),
                "formats_referenced": snip.get("formats_referenced", []),
            })
        (snippets_dir / "snippets_index.json").write_text(
            json.dumps(index_entries, indent=2, ensure_ascii=False),
            encoding="utf-8")
        LOG.info("Wrote %d snippets + snippets_index.json", len(self.snippets))


# ---------------------------------------------------------------------------
# CLI
# ---------------------------------------------------------------------------

def main():
    parser = argparse.ArgumentParser(
        description="Tree-sitter extraction engine for FOSS repositories")
    parser.add_argument("family", help="Product family (e.g. 3d, cells)")
    parser.add_argument("platform",
                        choices=list(PLATFORM_TO_LANG.keys()),
                        help="Target platform")
    parser.add_argument("repo_path", type=Path,
                        help="Path to the FOSS repository")
    parser.add_argument("output_dir", type=Path,
                        help="Directory to write extraction artifacts")
    parser.add_argument("-v", "--verbose", action="store_true",
                        help="Enable debug logging")
    args = parser.parse_args()

    logging.basicConfig(
        level=logging.DEBUG if args.verbose else logging.INFO,
        format="%(asctime)s %(name)s %(levelname)s %(message)s",
        datefmt="%H:%M:%S",
    )

    if not args.repo_path.is_dir():
        LOG.error("Repository path does not exist: %s", args.repo_path)
        sys.exit(1)

    scout = Scout(args.family, args.platform, args.repo_path, args.output_dir)
    scout.run()
    LOG.info("Done. Output written to %s", args.output_dir)


if __name__ == "__main__":
    main()
