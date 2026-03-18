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
    "cpp": {"class_specifier", "struct_specifier"},
    "python": {"class_definition"},
    "go": {"type_declaration", "type_spec"},
}

_FUNC_TYPES: dict[str, set[str]] = {
    "java": {"method_declaration", "constructor_declaration"},
    "csharp": {"method_declaration", "constructor_declaration",
               "property_declaration"},
    "javascript": {"function_declaration", "method_definition", "arrow_function"},
    "typescript": {"function_declaration", "method_definition", "arrow_function"},
    "go": {"function_declaration", "method_declaration"},
    "cpp": {"function_definition"},
    "python": {"function_definition"},
}

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
    # Apply same filtering as _detect_dotnet_root: prefer library over CLI/test
    candidates = []
    for cp in csproj_files:
        cp_text = cp.read_text(encoding="utf-8", errors="replace").lower()
        if "test" in cp.stem.lower():
            continue
        if "<outputtype>exe</outputtype>" in cp_text:
            continue
        candidates.append(cp)
    if not candidates:
        candidates = csproj_files
    candidates.sort(key=lambda p: len(p.parts))
    text = candidates[0].read_text(encoding="utf-8", errors="replace")
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
    gradle = repo / "build.gradle"
    if not info.get("name") and gradle.exists():
        text = gradle.read_text(encoding="utf-8", errors="replace")
        m = re.search(r"group\s*=\s*['\"]([^'\"]+)", text)
        if m:
            info["group_id"] = m.group(1)
        m = re.search(r"version\s*=\s*['\"]([^'\"]+)", text)
        if m:
            info["version"] = m.group(1)
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
        return not name.startswith("_")

    if language in ("javascript", "typescript"):
        parent = node.parent
        if parent and parent.type == "export_statement":
            return True
        # top-level declarations in modules are considered public
        if parent and parent.type in ("program", "module"):
            return True
        return False

    if language in ("java", "csharp", "cpp"):
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
    # C# uses field "returns"; Java uses field "type"
    if language in ("csharp", "java"):
        type_node = (child_by_field(node, "returns")   # csharp method_declaration
                     or child_by_field(node, "type"))  # java / fallback
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
        # Each "/// ..." line is a separate comment node; walk back
        # through all consecutive /// siblings to collect the full block.
        doc_lines: list[str] = []
        sib = prev
        while sib is not None:
            t = node_text(sib).strip()
            if t.startswith("///"):
                doc_lines.insert(0, t)
                sib = sib.prev_named_sibling or sib.prev_sibling
            else:
                break
        if doc_lines:
            joined = " ".join(line.lstrip("/ ").strip() for line in doc_lines)
            cleaned = re.sub(r"<[^>]+>", "", joined).strip()
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

_PYTHON_ENUM_BASES = {"Enum", "IntEnum", "StrEnum", "Flag", "IntFlag"}


def _is_python_enum(node) -> bool:
    """Check if a Python class_definition inherits from an Enum type."""
    if node.type != "class_definition":
        return False
    bases = _extract_bases(node, "python")
    return bool(set(bases) & _PYTHON_ENUM_BASES)


def _extract_enum_members(node, language: str) -> list[dict[str, str]]:
    """Extract enum constant names and values."""
    members: list[dict[str, str]] = []
    # child_by_field("body") handles C# (enum_member_declaration_list)
    # and Java (enum_body); fallbacks for other grammars
    body = (child_by_field(node, "body")
            or find_child_by_type(node, "enum_body")
            or find_child_by_type(node, "enum_member_declaration_list")
            or find_child_by_type(node, "enum_declaration_list")
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
    """Extract enum members from a Python IntEnum/Enum class body.

    Python enum members are assignment nodes directly in the class block:
        MEMBER = value
    Tree-sitter: class_definition > block > assignment > [identifier, value]
    """
    members: list[dict[str, str]] = []
    body = child_by_field(node, "body") or find_child_by_type(node, "block")
    if body is None:
        return members
    for ch in body.children:
        if ch.type != "assignment":
            continue
        left = child_by_field(ch, "left")
        right = child_by_field(ch, "right")
        if left and left.type == "identifier":
            name = node_text(left)
            if name.startswith("_"):
                continue
            val = node_text(right) if right else ""
            members.append({"name": name, "value": val})
    return members


# ---------------------------------------------------------------------------
# Core extraction
# ---------------------------------------------------------------------------

_TEST_DIR_PARTS = {"test", "tests", "test_", "__tests__", "spec", "specs"}


def _is_test_path(path: Path) -> bool:
    """Return True if the file lives inside a test directory."""
    return any(p.lower() in _TEST_DIR_PARTS or p.lower().endswith("test")
               or p.lower().endswith("tests")
               for p in path.parts[:-1])


def _collect_source_files(root: Path, ext: str, header_ext: str = "") -> list[Path]:
    """Glob for source files, capped at MAX_FILES, excluding test directories."""
    raw = list(root.rglob(f"*{ext}"))
    # Use path relative to root for test-path detection so that the scan root's
    # own location (e.g. tests/fixtures/repo) does not cause false positives.
    files = [f for f in raw if not _is_test_path(f.relative_to(root))][:MAX_FILES]
    if header_ext:
        raw_h = list(root.rglob(f"*{header_ext}"))
        files.extend([f for f in raw_h
                      if not _is_test_path(f.relative_to(root))][:MAX_FILES - len(files)])
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
        self._extract_module_constants()
        self._detect_formats()
        self._detect_limitations()
        self._extract_snippets()
        self._extract_doc_claims()
        self._build_identity_claims()
        self._build_class_graph()
        self._build_coverage()
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

            class_nodes = collect_nodes(root, class_types)

            for cnode in class_nodes:
                if not is_public(cnode, self.language):
                    continue

                cname = _node_name(cnode, self.language)
                if not cname:
                    continue

                is_enum = cnode.type in ("enum_declaration", "enum_definition")
                if not is_enum and self.language == "python":
                    is_enum = _is_python_enum(cnode)
                cdoc = _extract_doc_comment(cnode, self.language)
                bases = _extract_bases(cnode, self.language)
                if is_enum:
                    if self.language == "python":
                        enum_members = _extract_python_enum_members(cnode)
                    else:
                        enum_members = _extract_enum_members(cnode, self.language)
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

                    if mnode.type == "property_declaration":
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

                    methods.append({
                        "name": mname,
                        "params": params,
                        "return_type": ret,
                        "doc": mdoc,
                        "line": mnode.start_point[0] + 1,
                    })
                    self._add_claim(
                        "api_method",
                        f"{cname}.{mname}({', '.join(p['name'] for p in params)}) -> {ret}",
                        rel, mnode.start_point[0] + 1)

                # Python properties via decorators and typed class fields
                if self.language == "python":
                    self._extract_python_properties(cnode, cname, rel, properties)
                    if not is_enum:
                        self._extract_python_class_fields(cnode, cname, rel, properties)

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

                # Deduplicate: if same class name already recorded from a shorter
                # path (primary namespace), prefer that one; otherwise add.
                existing = next((c for c in self.classes if c["name"] == cname), None)
                if existing is not None:
                    if len(rel) < len(existing["file"]):
                        # Replace with shorter-path (more primary) version
                        self.classes.remove(existing)
                    else:
                        continue  # skip this duplicate
                if True:
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

    # -- Module-level constants --------------------------------------------

    def _extract_module_constants(self):
        """Extract module-level constants across all source files."""
        ext = _FILE_EXTENSIONS.get(self.language, ".py")
        files = _collect_source_files(self.pkg_root, ext)
        for fpath in files:
            rel = str(fpath.relative_to(self.repo)).replace("\\", "/")
            try:
                src = fpath.read_bytes()
            except OSError:
                continue
            tree = self.parser.parse(src)
            root = tree.root_node
            text = src.decode("utf-8", errors="replace")
            if self.language == "python":
                self._extract_python_constants(root, rel, text)

    def _extract_python_constants(self, root, rel: str, text: str):
        """Extract Python module-level constants: __all__ exports + UPPER_CASE."""
        # Parse __all__ to find explicitly exported names
        exported_names: set[str] = set()
        for node in root.children:
            assign = None
            if node.type == "expression_statement":
                assign = find_child_by_type(node, "assignment")
            elif node.type == "assignment":
                assign = node
            if assign is None:
                continue
            left = child_by_field(assign, "left")
            if left and node_text(left) == "__all__":
                right = child_by_field(assign, "right")
                if right and right.type == "list":
                    for item in right.children:
                        if item.type == "string":
                            name = node_text(item).strip("\"'")
                            exported_names.add(name)

        # Find UPPER_CASE assignments at root level
        class_names = {c["name"] for c in self.classes}
        for node in root.children:
            assign = None
            if node.type == "expression_statement":
                assign = find_child_by_type(node, "assignment")
            elif node.type == "assignment":
                assign = node
            if assign is None:
                continue
            left = child_by_field(assign, "left")
            right = child_by_field(assign, "right")
            if left is None or left.type != "identifier":
                continue
            name = node_text(left)
            if not name or name.startswith("_") or name == "__all__":
                continue
            # Skip class/function names already captured
            if name in class_names:
                continue

            is_exported = name in exported_names
            is_upper = bool(re.match(r'^[A-Z][A-Z0-9_]+$', name))
            if not is_exported and not is_upper:
                continue

            value = node_text(right) if right else ""
            if len(value) > 200:
                value = value[:200] + "..."

            self.constants.append({
                "name": name,
                "value": value,
                "file": rel,
                "line": assign.start_point[0] + 1,
                "exported": is_exported,
            })
            self._add_claim("api_constant",
                            f"Constant {name} = {value[:80]}",
                            rel, assign.start_point[0] + 1)

    def _extract_python_properties(self, cnode, cname: str, rel: str,
                                   properties: list[dict[str, Any]]):
        """Extract @property decorated methods in Python classes."""
        prop_names: set[str] = set()
        func_nodes = collect_nodes(cnode, {"function_definition"})
        for fn in func_nodes:
            # check for @property decorator
            dec = find_child_by_type(fn, "decorator")
            if dec is None:
                # check previous sibling (decorated_definition puts decorator there)
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
                "read_write": False,
            })
            prop_names.add(pname)
            self._add_claim("api_method",
                            f"{cname}.{pname} property of type {ret}",
                            rel, fn.start_point[0] + 1)

        # Second pass: detect @name.setter decorators
        if prop_names:
            decorated_nodes = collect_nodes(cnode, {"decorated_definition"})
            for dn in decorated_nodes:
                dec = find_child_by_type(dn, "decorator")
                if dec is None:
                    continue
                # setter decorator is: @ attribute(name.setter)
                attr = find_child_by_type(dec, "attribute")
                if attr is None:
                    continue
                # attribute has children: identifier("name") . identifier("setter")
                parts = [ch for ch in attr.children if ch.type == "identifier"]
                if len(parts) == 2 and node_text(parts[1]) == "setter":
                    setter_name = node_text(parts[0])
                    if setter_name in prop_names:
                        for prop in properties:
                            if prop["name"] == setter_name:
                                prop["read_write"] = True
                                break

    def _extract_python_class_fields(self, cnode, cname: str, rel: str,
                                      properties: list[dict[str, Any]]):
        """Extract typed class-level fields (dataclass fields, typed attributes).

        Captures patterns like: name: str, name: int = 0, items: list[str] = None
        AST: block > assignment with a 'type' child node.
        """
        existing_names = {p["name"] for p in properties}
        body = child_by_field(cnode, "body") or find_child_by_type(cnode, "block")
        if body is None:
            return
        for ch in body.children:
            if ch.type != "assignment":
                continue
            left = child_by_field(ch, "left")
            type_node = find_child_by_type(ch, "type")
            if left is None or type_node is None:
                continue
            if left.type != "identifier":
                continue
            field_name = node_text(left)
            if not field_name or field_name.startswith("_"):
                continue
            if field_name in existing_names:
                continue
            # Skip UPPER_CASE names (constants / enum members)
            if re.match(r'^[A-Z][A-Z0-9_]+$', field_name):
                continue
            field_type = node_text(type_node).lstrip(":").strip()
            properties.append({
                "name": field_name,
                "type": field_type,
                "line": ch.start_point[0] + 1,
                "kind": "field",
            })
            existing_names.add(field_name)
            self._add_claim("api_method",
                            f"{cname}.{field_name} field of type {field_type}",
                            rel, ch.start_point[0] + 1)

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
                is_enum = cn.type in ("enum_declaration", "enum_definition")
                if not is_enum and self.language == "python":
                    is_enum = _is_python_enum(cn)

                if format_pattern.search(cname):
                    if is_enum:
                        # Only enum members are concrete format names
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
                    # Non-enum format-named classes (e.g. FileFormat, FileFormatType)
                    # are framework types, not concrete format entries — skip them.

                if importer_pattern.search(cname):
                    # Skip pure interface declarations (IExporter, IImporter)
                    if cname.startswith("I") and cname[1:2].isupper() and cn.type == "interface_declaration":
                        pass
                    else:
                        direction = "import"
                        if re.search(r"(Exporter|Writer|Saver)", cname, re.IGNORECASE):
                            direction = "export"
                        fmt_name = re.sub(
                            r"(Importer|Exporter|Reader|Writer|Loader|Saver)", "",
                            cname, flags=re.IGNORECASE).strip()
                        # Skip if stripped name is empty, a single char, or
                        # looks like a bare interface prefix ("I")
                        if fmt_name and len(fmt_name) > 1:
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

        # Secondary pass: detect formats from method names (to_X, from_X, etc.)
        _FMT_METHOD_RE = re.compile(
            r'^(to|from|save_as|load|export_to|import_from)_(\w+)$', re.IGNORECASE)
        _FMT_SKIP = {"file", "stream", "bytes", "string", "dict", "json",
                      "text", "list", "tuple", "set", "int", "float", "bool",
                      "path", "buffer", "io", "reader", "writer", "document",
                      "object", "array", "map", "iterator", "config",
                      "embedded_message"}
        seen_formats = {f["format"].lower() for f in self.formats}
        for cls in self.classes:
            for method in cls.get("methods", []):
                m = _FMT_METHOD_RE.match(method["name"])
                if not m:
                    continue
                direction_word = m.group(1).lower()
                fmt_name = m.group(2)
                fmt_lower = fmt_name.lower()
                if fmt_lower in _FMT_SKIP:
                    continue
                # Skip names ending with internal suffixes
                if fmt_lower.endswith(("_document", "_reader", "_writer",
                                       "_object", "_stream")):
                    continue
                if fmt_lower in seen_formats:
                    continue
                direction = ("export" if direction_word in ("to", "save_as", "export_to")
                             else "import")
                self.formats.append({
                    "format": fmt_name,
                    "enum": "",
                    "value": "",
                    "file": cls["file"],
                    "line": method["line"],
                    "direction": direction,
                    "detected_via": f"{cls['name']}.{method['name']}",
                })
                seen_formats.add(fmt_name.lower())
                self._add_claim(
                    "format_support",
                    f"{direction} support for {fmt_name} via {cls['name']}.{method['name']}()",
                    cls["file"], method["line"])

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
        snippet_dirs = ["tests", "test", "examples", "example", "samples"]
        ext = _FILE_EXTENSIONS.get(self.language, ".py")

        for sdir in snippet_dirs:
            d = self.repo / sdir
            if not d.is_dir():
                continue
            files = list(d.rglob(f"*{ext}"))[:100]
            for fpath in files:
                rel = str(fpath.relative_to(self.repo)).replace("\\", "/")
                try:
                    src = fpath.read_bytes()
                except OSError:
                    continue
                tree = self.parser.parse(src)
                has_error = tree.root_node.has_error
                text = src.decode("utf-8", errors="replace")
                self.snippets.append({
                    "file": rel,
                    "language": self.language,
                    "code": text[:5000],
                    "valid": not has_error,
                })

        # README fenced code blocks
        for readme_name in ("README.md", "readme.md", "README.rst"):
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
                    code = m.group(2)
                    # validate via tree-sitter parse
                    t = self.parser.parse(code.encode("utf-8"))
                    valid = not t.root_node.has_error
                    self.snippets.append({
                        "file": readme_name,
                        "language": self.language,
                        "code": code[:5000],
                        "valid": valid,
                    })
                break

    # -- Documentation claims ----------------------------------------------

    _DOC_FILES = [
        "PUBLIC_API.md", "API.md", "FEATURES.md", "USAGE.md", "GUIDE.md",
        "docs/API.md", "docs/README.md",
    ]

    def _extract_doc_claims(self):
        """Extract structured claims and code snippets from documentation files."""
        for doc_name in self._DOC_FILES:
            doc_path = self.repo / doc_name
            if not doc_path.exists():
                continue
            try:
                text = doc_path.read_text(encoding="utf-8", errors="replace")
            except OSError:
                continue

            claim_count = 0
            for i, line in enumerate(text.splitlines(), 1):
                stripped = line.strip()
                if stripped.startswith(("- ", "* ", "• ")) and len(stripped) > 10:
                    claim_text = stripped.lstrip("-*• ").strip()
                    if len(claim_text) > 200:
                        claim_text = claim_text[:200]
                    self._add_claim("doc_feature", claim_text, doc_name, i)
                    claim_count += 1
                    if claim_count >= 100:
                        break

            # Extract fenced code blocks as additional snippets
            lang_names = {self.language}
            if self.language == "python":
                lang_names.update({"python", "py"})
            elif self.language == "csharp":
                lang_names.update({"csharp", "cs", "c#"})
            elif self.language == "javascript":
                lang_names.update({"javascript", "js"})
            elif self.language == "typescript":
                lang_names.update({"typescript", "ts"})
            elif self.language == "cpp":
                lang_names.update({"cpp", "c++"})

            fence_re = re.compile(
                r"```(" + "|".join(re.escape(n) for n in lang_names)
                + r")\s*\n(.*?)```", re.DOTALL | re.IGNORECASE)
            for m in fence_re.finditer(text):
                code = m.group(2)
                self.snippets.append({
                    "file": doc_name,
                    "language": self.language,
                    "code": code[:5000],
                    "valid": True,
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

    def _build_test_index(self) -> set[str]:
        """Return set of class names referenced in any test-directory source file."""
        ext = _FILE_EXTENSIONS.get(self.language, ".py")
        tested: set[str] = set()
        class_names = {c["name"] for c in self.classes if c.get("kind") != "function"}
        try:
            for fpath in self.repo.rglob(f"*{ext}"):
                if not _is_test_path(fpath):
                    continue
                try:
                    text = fpath.read_text(encoding="utf-8", errors="replace")
                except OSError:
                    continue
                for name in class_names:
                    if name in text:
                        tested.add(name)
        except Exception:
            pass
        return tested

    def _build_coverage(self):
        tested = self._build_test_index()
        for cls in self.classes:
            if cls.get("kind") == "function":
                continue
            self.coverage.append({
                "class": cls["name"],
                "file": cls["file"],
                "method_count": len(cls.get("methods", [])),
                "property_count": len(cls.get("properties", [])),
                "has_doc": bool(cls.get("doc")),
                "has_tests": cls["name"] in tested,
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
        return ""

    def _write_outputs(self):
        self.output.mkdir(parents=True, exist_ok=True)

        # model.yaml
        class_count = sum(1 for c in self.classes if c.get("kind") != "function")
        method_count = sum(len(c.get("methods", [])) for c in self.classes)
        prop_count = sum(len(c.get("properties", [])) for c in self.classes)
        enum_count = sum(1 for c in self.classes if c.get("enum_members"))

        model = {
            "family": self.family,
            "platform": self.platform,
            "product_name": self.manifest.get("name", f"Aspose.{self.family.upper()}-FOSS for {self.platform}"),
            "version": self.manifest.get("version", ""),
            "license": self.manifest.get("license", ""),
            "repo_sha": self._get_repo_sha(),
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
                "constant_count": len(self.constants),
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

        # constants.json
        (self.output / "constants.json").write_text(
            json.dumps(self.constants, indent=2, ensure_ascii=False),
            encoding="utf-8")
        LOG.info("Wrote constants.json (%d constants)", len(self.constants))

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

        # snippets/
        snippets_dir = self.output / "snippets"
        snippets_dir.mkdir(exist_ok=True)
        for i, snip in enumerate(self.snippets):
            fname = f"snippet_{i:04d}_{Path(snip['file']).stem}"
            ext = _FILE_EXTENSIONS.get(snip["language"], ".txt")
            out_path = snippets_dir / f"{fname}{ext}"
            out_path.write_text(snip["code"], encoding="utf-8")
        LOG.info("Wrote %d snippets", len(self.snippets))


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
