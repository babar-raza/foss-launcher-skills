"""extraction/api_surface.py — API surface extraction from source trees.

Extracted from scout.py (steps 4.7). Standalone functions usable without the
Scout class.

Public API::

    extract_api_surface(parser, language, pkg_root, repo, family)
        -> tuple[list[dict], list[dict], list[str], set[str]]
        # (classes, claims, scanned_files, packages)
"""
from __future__ import annotations

import hashlib
import re
from pathlib import Path
from typing import Any

from extraction.tree_helpers import (
    _CLASS_TYPES,
    _DOC_COMMENT_STYLES,
    _FILE_EXTENSIONS,
    _FUNC_TYPES,
    _HEADER_EXTENSIONS,
    _MODULE_TYPES,
    _PY_ENUM_BASES,
    _collect_source_files,
    _extract_bases,
    _extract_enum_members,
    _extract_python_enum_members,
    _node_name,
    child_by_field,
    collect_nodes,
    find_child_by_type,
    is_public,
    node_text,
)


# ---------------------------------------------------------------------------
# Internal claim helper
# ---------------------------------------------------------------------------

def _make_claim(family: str, kind: str, text: str,
                file: str = "", line: int = 0) -> dict:
    h = hashlib.sha256(text.encode("utf-8")).hexdigest()[:6]
    evidence = [{"file": file, "line": line}] if file else []
    return {
        "claim_id": f"CLM-{family}-{h}",
        "kind": kind,
        "text": text,
        "confidence": 1.0,
        "claim_source": "scout",
        "evidence": evidence,
    }


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
                        "identifier", "parameter_declaration",
                        "optional_parameter_declaration"):
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

            # C++: parameter_declaration uses a "declarator" field for the name.
            # Handles default-arg forms: std::string x = {}, const T& y = T()
            if not pname and ch.type == "parameter_declaration":
                decl = child_by_field(ch, "declarator")
                if decl is not None:
                    cur = decl
                    while cur is not None and cur.type != "identifier":
                        inner = child_by_field(cur, "declarator")
                        if inner is not None:
                            cur = inner
                        else:
                            found = None
                            for gc in cur.children:
                                if gc.type == "identifier":
                                    found = gc
                                    break
                            cur = found
                    if cur is not None and cur.type == "identifier":
                        pname = node_text(cur)

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

    # C#/Java/C++: type before method name
    if language in ("csharp", "java", "cpp"):
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

def _first_sentence(text: str) -> str:
    """Return the first sentence (up to first period-space or newline)."""
    text = text.strip()
    m = re.match(r"^(.+?[.!?])(?:\s|$)", text, re.DOTALL)
    if m:
        return m.group(1).strip()
    # no sentence-ending punctuation; return first line
    return text.split("\n")[0].strip()[:200]


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


# ---------------------------------------------------------------------------
# Python property extraction
# ---------------------------------------------------------------------------

def _extract_python_properties(
    cnode, cname: str, rel: str, family: str,
) -> tuple[list[dict[str, Any]], list[dict]]:
    """Extract @property decorated methods in Python classes.

    Returns (properties, claims).
    """
    properties: list[dict[str, Any]] = []
    claims: list[dict] = []

    func_nodes = collect_nodes(cnode, {"function_definition"})
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
        })
        claims.append(_make_claim(
            family, "api_method",
            f"{cname}.{pname} property of type {ret}",
            rel, fn.start_point[0] + 1))

    return properties, claims


# ---------------------------------------------------------------------------
# Java property synthesis
# ---------------------------------------------------------------------------

_JAVA_OBJECT_METHODS: frozenset[str] = frozenset({
    "getClass", "hashCode", "equals", "toString",
    "notify", "notifyAll", "wait", "clone", "finalize",
})


def _synthesize_java_properties(
    methods: list[dict[str, Any]], cname: str, rel: str, family: str,
) -> tuple[list[dict[str, Any]], list[dict]]:
    """Synthesize property entries from Java getter/setter method pairs.

    Returns (properties, claims).
    """
    properties: list[dict[str, Any]] = []
    claims: list[dict] = []

    getters: dict[str, dict[str, Any]] = {}
    for m in methods:
        name = m["name"]
        if name in _JAVA_OBJECT_METHODS:
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
        claims.append(_make_claim(
            family, "api_method",
            f"{cname}.{prop_name} property of type {ptype}",
            rel, getter["line"]))

    return properties, claims


# ---------------------------------------------------------------------------
# C++ property synthesis
# ---------------------------------------------------------------------------

def _synthesize_cpp_properties(
    methods: list[dict[str, Any]], cname: str, rel: str, family: str,
) -> tuple[list[dict[str, Any]], list[dict]]:
    """Synthesize property entries from C++ getter/setter method pairs.

    The Aspose FOSS C++ headers use snake_case conventions:
      - Getter: a public method ``<name>(...)`` with 0 params and a non-void
        return type that does NOT begin with ``set_``.
      - Setter: a public method ``set_<name>(T val)`` with exactly 1 param.

    A virtual property ``<name>`` is emitted for every getter.  If a matching
    ``set_<name>`` setter exists the property is considered read-write;
    otherwise it is read-only (no effect on the emitted record — callers can
    inspect the setter list if needed).

    Returns (properties, claims).
    """
    properties: list[dict[str, Any]] = []
    claims: list[dict] = []

    # Collect setters first so we can annotate read-write properties.
    setter_names: set[str] = set()
    for m in methods:
        name = m["name"]
        params = m.get("params", [])
        if name.startswith("set_") and len(name) > 4 and len(params) == 1:
            setter_names.add(name[4:])  # strip "set_" prefix

    seen: set[str] = set()
    for m in methods:
        name = m["name"]
        params = m.get("params", [])
        ret = m.get("return_type", "")

        # Skip setters (they are not independent properties)
        if name.startswith("set_"):
            continue
        # Must have 0 parameters and a non-empty, non-void return type
        if len(params) != 0:
            continue
        if not ret or ret.strip() in ("void", ""):
            continue
        # Skip private/internal helpers (leading underscore convention)
        if name.startswith("_"):
            continue
        # De-duplicate (e.g. const and non-const overloads share the same name)
        if name in seen:
            continue
        seen.add(name)

        properties.append({
            "name": name,
            "type": ret,
            "line": m["line"],
            "writable": name in setter_names,
        })
        claims.append(_make_claim(
            family, "api_method",
            f"{cname}.{name} property of type {ret}",
            rel, m["line"]))

    return properties, claims


# ---------------------------------------------------------------------------
# Core API surface extraction
# ---------------------------------------------------------------------------

def extract_api_surface(
    parser,
    language: str,
    pkg_root: Path,
    repo: Path,
    family: str,
) -> tuple[list[dict[str, Any]], list[dict], list[str], set[str]]:
    """Extract API classes, methods, and properties from source files.

    Returns (classes, claims, scanned_files, packages).
    """
    classes: list[dict[str, Any]] = []
    claims: list[dict] = []
    scanned_files: list[str] = []
    packages: set[str] = set()

    ext = _FILE_EXTENSIONS.get(language, ".py")
    header_ext = _HEADER_EXTENSIONS.get(language, "")
    files = _collect_source_files(pkg_root, ext, header_ext)

    class_types = _CLASS_TYPES.get(language, set())
    func_types = _FUNC_TYPES.get(language, set())

    for fpath in files:
        rel = str(fpath.relative_to(repo)).replace("\\", "/")
        try:
            src = fpath.read_bytes()
        except OSError:
            continue

        tree = parser.parse(src)
        root = tree.root_node
        scanned_files.append(rel)

        # Track packages/namespaces
        module_types = _MODULE_TYPES.get(language, set())
        for mnode in collect_nodes(root, module_types):
            # C++ namespace_definition: extract name field instead of full text
            if language == "cpp" and mnode.type == "namespace_definition":
                name_node = child_by_field(mnode, "name")
                if name_node:
                    packages.add(node_text(name_node))
                continue
            pkg_text = node_text(mnode).strip().rstrip(";").rstrip("{").strip()
            for kw in ("package", "namespace"):
                if pkg_text.startswith(kw):
                    pkg_text = pkg_text[len(kw):].strip()
            if pkg_text:
                packages.add(pkg_text)

        class_nodes = collect_nodes(root, class_types)

        for cnode in class_nodes:
            if not is_public(cnode, language):
                continue

            cname = _node_name(cnode, language)
            if not cname:
                continue

            # Skip C++ forward declarations (class Foo;) — no body
            if (language == "cpp"
                    and cnode.type in ("class_specifier", "struct_specifier")
                    and find_child_by_type(cnode, "field_declaration_list") is None):
                continue

            is_enum = cnode.type in ("enum_declaration", "enum_definition",
                                     "enum_specifier")
            cdoc = _extract_doc_comment(cnode, language)
            bases = _extract_bases(cnode, language)

            # Python: detect enums by base class inheritance
            if not is_enum and language == "python":
                if set(bases) & _PY_ENUM_BASES:
                    is_enum = True

            if is_enum:
                if language == "python":
                    enum_members = _extract_python_enum_members(cnode)
                else:
                    enum_members = _extract_enum_members(cnode, language)
            elif language == "python":
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
                if not is_public(mnode, language):
                    continue
                mname = _node_name(mnode, language)
                if not mname:
                    continue

                # Skip Python @property and setter/deleter — handled by _extract_python_properties
                if language == "python" and mnode.type == "function_definition":
                    dec = find_child_by_type(mnode, "decorator")
                    if dec is None:
                        prev = mnode.prev_named_sibling
                        if prev and prev.type == "decorator":
                            dec = prev
                    if dec is not None:
                        dec_text = node_text(dec)
                        if "@property" in dec_text or ".setter" in dec_text or ".deleter" in dec_text:
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
                    claims.append(_make_claim(
                        family, "api_method",
                        f"{cname}.{mname} property of type {ptype}",
                        rel, mnode.start_point[0] + 1))
                    continue

                params = _extract_method_params(mnode, language)
                ret = _extract_return_type(mnode, language)
                mdoc = _extract_doc_comment(mnode, language)

                is_ctor = (mnode.type == "constructor_declaration"
                           or (language == "python" and mname == "__init__")
                           or (language in ("typescript", "javascript")
                               and mname == "constructor"))

                methods.append({
                    "name": mname,
                    "params": params,
                    "return_type": ret,
                    "doc": mdoc,
                    "line": mnode.start_point[0] + 1,
                    "is_constructor": is_ctor,
                })
                claims.append(_make_claim(
                    family, "api_method",
                    f"{cname}.{mname}({', '.join(p['name'] for p in params)}) -> {ret}",
                    rel, mnode.start_point[0] + 1))

            # Python properties via decorators
            if language == "python":
                extra_props, extra_claims = _extract_python_properties(
                    cnode, cname, rel, family)
                properties.extend(extra_props)
                claims.extend(extra_claims)

            # Java properties via getter/setter synthesis
            if language == "java":
                extra_props, extra_claims = _synthesize_java_properties(
                    methods, cname, rel, family)
                properties.extend(extra_props)
                claims.extend(extra_claims)

            # C++ properties via getter/setter synthesis
            if language == "cpp":
                extra_props, extra_claims = _synthesize_cpp_properties(
                    methods, cname, rel, family)
                properties.extend(extra_props)
                claims.extend(extra_claims)

            # C++ field_declaration method declarations (no body)
            if language == "cpp":
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
                            params = _extract_method_params(fdecl, language)
                            ret = _extract_return_type(member, language)
                            mdoc = _extract_doc_comment(member, language)
                            methods.append({
                                "name": mname,
                                "params": params,
                                "return_type": ret,
                                "doc": mdoc,
                                "line": member.start_point[0] + 1,
                                "is_constructor": False,
                            })
                            claims.append(_make_claim(
                                family, "api_method",
                                f"{cname}.{mname}({', '.join(p['name'] for p in params)}) -> {ret}",
                                rel, member.start_point[0] + 1))

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

            classes.append(cls_record)
            claims.append(_make_claim(
                family, "api_class",
                f"Class {cname} defined in {rel}",
                rel, cnode.start_point[0] + 1))

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
            if not is_public(fnode, language):
                continue
            fname = _node_name(fnode, language)
            if not fname:
                continue
            params = _extract_method_params(fnode, language)
            ret = _extract_return_type(fnode, language)
            fdoc = _extract_doc_comment(fnode, language)

            classes.append({
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
            claims.append(_make_claim(
                family, "api_method",
                f"Function {fname}({', '.join(p['name'] for p in params)}) -> {ret}",
                rel, fnode.start_point[0] + 1))

    return classes, claims, scanned_files, packages
